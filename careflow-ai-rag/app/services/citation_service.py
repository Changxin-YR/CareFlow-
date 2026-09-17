"""Citation 服务 —— 反幻觉引用的唯一构造点。

核心原则（契约 §18）：

* Citation **不由 LLM 自由生成**；
* 必须先有「本轮真实检索命中」，再由程序读取 manifest 的
  `document_id / section / source_url` 构造；
* 任何一条引用都要通过三重校验：文档存在于 manifest、`status=active`、
  该文档（或该 chunk）在本轮检索结果中；
* 非法引用被删除并记录日志（进入 `dropped_citations` 供审计）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging_config import get_logger, log_event
from app.schemas.common import Citation, RetrievedChunk
from app.schemas.rag import DroppedCitation
from app.services.manifest_service import KnowledgeStore, get_knowledge_store

logger = get_logger("services.citation")

#: 引用原文截断长度
QUOTE_MAX_CHARS = 160
#: 没有显式标记时，最多给出几条引用
DEFAULT_MAX_CITATIONS = 3


@dataclass
class CitationResult:
    citations: list[Citation] = field(default_factory=list)
    dropped: list[DroppedCitation] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)


class CitationService:
    """基于真实检索命中构造并校验 Citation。"""

    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self.store = store or get_knowledge_store()

    # ------------------------------------------------------------------ 构造
    def build(
        self,
        hits: list[RetrievedChunk],
        *,
        used_markers: list[int] | None = None,
        used_chunk_ids: list[str] | None = None,
        max_citations: int = DEFAULT_MAX_CITATIONS,
    ) -> CitationResult:
        """从真实命中构造引用。

        :param used_markers: LLM 回答中出现的 `[n]` 编号（1-based，对应 hits 顺序）
        :param used_chunk_ids: LLM 显式声明使用的 chunk_id（仍须能在本轮命中里找到）
        """
        result = CitationResult()
        if not hits:
            return result

        selected: list[RetrievedChunk] = []
        seen: set[str] = set()

        def _push(hit: RetrievedChunk) -> None:
            if hit.chunk_id in seen:
                return
            seen.add(hit.chunk_id)
            selected.append(hit)

        if used_markers:
            for marker in used_markers:
                index = int(marker) - 1
                if 0 <= index < len(hits):
                    _push(hits[index])
                else:
                    result.dropped.append(
                        DroppedCitation(
                            reason="marker_out_of_range",
                            detail={"marker": marker, "hits": len(hits)},
                        )
                    )
        if used_chunk_ids:
            by_id = {hit.chunk_id: hit for hit in hits}
            for chunk_id in used_chunk_ids:
                hit = by_id.get(str(chunk_id))
                if hit is None:
                    result.dropped.append(
                        DroppedCitation(
                            reason="chunk_not_retrieved_this_round",
                            chunk_id=str(chunk_id),
                        )
                    )
                    continue
                _push(hit)
        if not selected:
            # 未显式标注 → 采用 Top-N 命中作为依据（仍然是真实命中）
            for hit in hits[:max_citations]:
                _push(hit)

        for hit in selected:
            citation = self._validate(hit, result)
            if citation is not None:
                result.citations.append(citation)

        result.citations = result.citations[:max_citations]
        result.document_ids = sorted({item.document_id for item in result.citations})
        return result

    # ------------------------------------------------------------------ 校验
    def _validate(self, hit: RetrievedChunk, result: CitationResult) -> Citation | None:
        document_id = (hit.document_id or "").strip()
        if not document_id:
            result.dropped.append(
                DroppedCitation(reason="missing_document_id", chunk_id=hit.chunk_id)
            )
            log_event(
                logger,
                "citation dropped",
                operation="citation",
                success=False,
                error_code="missing_document_id",
                chunk_id=hit.chunk_id,
            )
            return None

        entry = self.store.get(document_id)
        if entry is None:
            result.dropped.append(
                DroppedCitation(
                    reason="document_not_in_manifest",
                    document_id=document_id,
                    chunk_id=hit.chunk_id,
                )
            )
            log_event(
                logger,
                "citation dropped",
                operation="citation",
                success=False,
                error_code="document_not_in_manifest",
                document_ids=[document_id],
            )
            return None

        if not entry.is_active:
            result.dropped.append(
                DroppedCitation(
                    reason="document_not_active",
                    document_id=document_id,
                    chunk_id=hit.chunk_id,
                    detail={"status": entry.status},
                )
            )
            log_event(
                logger,
                "citation dropped",
                operation="citation",
                success=False,
                error_code="document_not_active",
                document_ids=[document_id],
                status=entry.status,
            )
            return None

        # 本轮确实被检索：chunk 必须来自该文档，或（千帆 KB 场景）至少文档命中
        chunk = self.store.get_chunk(hit.chunk_id)
        if chunk is not None and chunk.document_id != document_id:
            result.dropped.append(
                DroppedCitation(
                    reason="chunk_document_mismatch",
                    document_id=document_id,
                    chunk_id=hit.chunk_id,
                )
            )
            return None

        # source_url / 权威信息以 manifest 为准（文档可能有更新，抓取侧不得覆写）
        source_url = entry.source_url or hit.source_url
        if not source_url.startswith("http"):
            result.dropped.append(
                DroppedCitation(
                    reason="manifest_source_url_missing",
                    document_id=document_id,
                    chunk_id=hit.chunk_id,
                )
            )
            return None

        content = hit.content or (chunk.content if chunk else "")
        quote = content[:QUOTE_MAX_CHARS]
        return Citation(
            document_id=document_id,
            chunk_id=hit.chunk_id,
            title=entry.title or hit.title,
            section=hit.section or (chunk.section if chunk else ""),
            authority=entry.authority,
            authority_level=entry.authority_level,
            version=entry.version,
            effective_date=entry.effective_date,
            source_url=source_url,
            quote=quote,
        )

    # ------------------------------------------------------------------ 工具
    def verify_citation(self, citation: Citation) -> tuple[bool, str]:
        """公开校验接口（测试与业务后端复核用）。"""
        dummy = CitationResult()
        hit = RetrievedChunk(
            chunk_id=citation.chunk_id,
            document_id=citation.document_id,
            title=citation.title,
            section=citation.section,
            source_url=citation.source_url,
            content=citation.quote,
        )
        validated = self._validate(hit, dummy)
        if validated is None:
            return False, dummy.dropped[0].reason if dummy.dropped else "unknown"
        return True, ""
