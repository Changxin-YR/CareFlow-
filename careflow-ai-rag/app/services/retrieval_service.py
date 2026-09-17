"""检索服务：本地 BM25 + 可选千帆知识库，混合排序与上下文构建。

完整检索流程（契约 §15）::

    Query → Normalization → Domain Router → Metadata Filter
          → Vector/BM25 Retrieval → Hybrid Retrieval → Top-K
          → 去重 → 权威过滤 → Context Builder

* 本地模式（`AI_PROVIDER=mock` 或未配置千帆 KB）只跑 BM25；
* 千帆模式下会额外调用千帆知识库检索，与本地结果做 RRF 风格融合；
* `AI_PROVIDER=qianfan` 但 KB 检索不可用时**自动降级**为纯本地检索，
  并在响应 `meta.degraded` 中如实标注。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.clients.base import LLMClient
from app.core.config import AUTHORITY_RANK, KB_IDS, Settings, load_settings
from app.core.errors import CareFlowError
from app.core.logging_config import get_logger, log_event
from app.schemas.common import RetrievedChunk
from app.services.manifest_service import Chunk, KnowledgeStore, get_knowledge_store

logger = get_logger("services.retrieval")

CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
ASCII_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._\-/%]*")
PUNCT_RE = re.compile(r"[\s\u3000]+")

#: 等级加权：同分时高权威优先（P0 > P1 > P2 > P3 > P4）
AUTHORITY_BOOST: dict[str, float] = {
    "P0": 1.25,
    "P1": 1.15,
    "P2": 1.05,
    "P3": 1.00,
    "P4": 0.95,
}

#: 高频无区分度的中文二元组（避免"怎么/什么"造成假命中）
STOP_BIGRAMS = {
    "怎么", "什么", "如何", "可以", "应该", "需要", "是否", "有没有",
    "哪些", "多少", "为什", "什 么", "一个", "我们", "他们", "这个",
}


def normalize_query(text: str) -> str:
    """查询归一化：全角转半角 + 压缩空白 + 统一符号。"""
    if not text:
        return ""
    chars: list[str] = []
    for char in text:
        code = ord(char)
        if code == 0x3000:
            chars.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            chars.append(chr(code - 0xFEE0))
        else:
            chars.append(char)
    normalized = "".join(chars).replace("／", "/").replace("～", "~").lower()
    return PUNCT_RE.sub(" ", normalized).strip()


def tokenize(text: str) -> list[str]:
    """中文按字级二元组切分（无需第三方分词器），英文/数字按词切分。"""
    if not text:
        return []
    lowered = text.lower()
    tokens: list[str] = []
    for run in CJK_RUN_RE.findall(lowered):
        if len(run) == 1:
            tokens.append(run)
            continue
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if bigram not in STOP_BIGRAMS:
                tokens.append(bigram)
        if len(run) <= 6:
            tokens.append(run)  # 短术语整体保留，提升专有名词权重
    tokens.extend(ASCII_TOKEN_RE.findall(lowered))
    return tokens


def query_terms(text: str) -> set[str]:
    return set(tokenize(text))


class BM25Index:
    """轻量 BM25 索引（内存态，随 KnowledgeStore 重建）。"""

    def __init__(self, chunks: list[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.chunk_ids: list[str] = []
        self.term_freqs: list[Counter[str]] = []
        self.doc_freq: Counter[str] = Counter()
        self.doc_lengths: list[int] = []
        self.documents: list[Chunk] = []
        self._build(chunks)

    #: 标题 / 章节词在 BM25 的 tf 上额外计几次（字段加权）
    HEAD_FIELD_BOOST = 3

    def _build(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            tokens = tokenize(f"{chunk.title} {chunk.section} {chunk.content}")
            if not tokens:
                continue
            counter = Counter(tokens)
            # 字段加权：标题/章节命中比正文命中更有指示性。
            # 典型作用：`WHO PEN 是什么？` 里 "who" 在全部 WHO 切片中都出现（页眉），
            # IDF 极低；只有标题里的 "WHO PEN" 才是真正的判别信号。
            head_tokens = tokenize(f"{chunk.title} {chunk.section}")
            for term in head_tokens:
                counter[term] += self.HEAD_FIELD_BOOST
            self.documents.append(chunk)
            self.chunk_ids.append(chunk.chunk_id)
            self.term_freqs.append(counter)
            self.doc_lengths.append(sum(counter.values()))
            for term in counter:
                self.doc_freq[term] += 1
        self.total_docs = len(self.documents)
        self.avg_length = (
            sum(self.doc_lengths) / self.total_docs if self.total_docs else 0.0
        )

    @property
    def is_empty(self) -> bool:
        return self.total_docs == 0

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1.0 + (self.total_docs - df + 0.5) / (df + 0.5))

    def usable_query_terms(
        self, query: str, allowed_ids: set[str] | None = None
    ) -> dict[str, float]:
        """返回查询中**在本次检索范围内有区分度**（df>0）的词及其 IDF。

        `allowed_ids=None` 表示全语料。给定域过滤时，只在子集内统计 df ——
        因为子集里根本不存在的词不可能被命中，把它计入分母会让
        「中文描述 + 英文缩写」这类跨语言查询的覆盖率被永久压垮。
        """
        terms = set(tokenize(normalize_query(query)))
        if allowed_ids is None:
            return {term: self._idf(term) for term in terms if self._idf(term) > 0.0}

        indexes = [
            i for i, doc in enumerate(self.documents) if doc.document_id in allowed_ids
        ]
        subset_n = len(indexes)
        if not subset_n:
            return {}
        out: dict[str, float] = {}
        for term in terms:
            df = sum(1 for i in indexes if term in self.term_freqs[i])
            if df > 0:
                out[term] = math.log(1.0 + (subset_n - df + 0.5) / (df + 0.5))
        return out

    def search(
        self, query: str, *, allowed_ids: set[str] | None = None
    ) -> list[tuple[Chunk, float, int]]:
        """返回 ``[(chunk, bm25_score, matched_term_count), ...]``，按分数降序。"""
        terms = tokenize(normalize_query(query))
        if not terms:
            return []
        unique_terms = set(terms)
        idf_cache = {term: self._idf(term) for term in unique_terms}
        usable_terms = {term for term, idf in idf_cache.items() if idf > 0.0}
        if not usable_terms:
            return []

        scored: list[tuple[Chunk, float, int]] = []
        for position, chunk in enumerate(self.documents):
            if allowed_ids is not None and chunk.document_id not in allowed_ids:
                continue
            counter = self.term_freqs[position]
            matched = [term for term in usable_terms if term in counter]
            if not matched:
                continue
            length = self.doc_lengths[position] or 1
            score = 0.0
            for term in matched:
                freq = counter[term]
                denominator = freq + self.k1 * (
                    1 - self.b + self.b * length / (self.avg_length or 1.0)
                )
                score += idf_cache[term] * (freq * (self.k1 + 1)) / denominator
            # 命中术语覆盖率加成：避免长文档靠堆词刷分
            coverage = len(matched) / max(1, len(usable_terms))
            score *= 0.6 + 0.4 * coverage
            scored.append((chunk, score, len(matched)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored


@dataclass
class RetrievalResult:
    hits: list[RetrievedChunk] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False
    notes: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    best_score: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not self.hits


class RetrievalService:
    """检索编排器。"""

    def __init__(
        self,
        store: KnowledgeStore | None = None,
        client: LLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.store = store or get_knowledge_store(self.settings)
        self.client = client
        self._index: BM25Index | None = None
        self._index_size = -1

    # ------------------------------------------------------------------ 索引
    @property
    def index(self) -> BM25Index:
        if self._index is None or self._index_size != len(self.store.chunks):
            self._index = BM25Index(self.store.chunks)
            self._index_size = len(self.store.chunks)
        return self._index

    # ------------------------------------------------------------------ 检索
    async def search(
        self,
        query: str,
        *,
        domains: list[str] | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> RetrievalResult:
        self.store.load()
        normalized = normalize_query(query)
        result = RetrievalResult(domains=list(domains or []), terms=sorted(query_terms(normalized))[:40])
        if not normalized:
            return result

        top_k = top_k or self.settings.rag_top_k

        # 注意：不能写 `allowed_ids or None` —— 空集合是 falsy，会被当成"不过滤"，
        # 从而把显式限定的域静默放大成全库检索。这里显式区分两种情况。
        allowed_ids: set[str] | None
        if domains:
            allowed_ids = self.store.documents_for_domains(domains)
            if not allowed_ids:
                result.notes.append(
                    f"显式指定的知识域 {sorted(domains)} 在 manifest 中没有任何文档，判定为无证据"
                )
                log_event(
                    logger,
                    "domain filter matched no documents",
                    operation="retrieve",
                    success=True,
                    error_code="",
                    domains=list(domains),
                )
                return result
        else:
            allowed_ids = None

        local_hits: list[tuple[Chunk, float]] = []
        if not self.index.is_empty:
            raw_hits = self.index.search(normalized, allowed_ids=allowed_ids)
            # 相关性闸门：BM25 在中文大语料上会被"怎么/今天/适合"这类高频二元组带出假命中，
            # 因此要求「分数达标」且「命中词数达标」，否则按无证据处理（无答案 > 编造答案）
            floor = self.settings.rag_min_relevance_score
            min_terms = self.settings.rag_min_matched_terms
            min_coverage = self.settings.rag_min_term_coverage
            usable = self.index.usable_query_terms(normalized, allowed_ids)
            usable_count = max(1, len(usable))
            gated = 0
            for chunk, score, matched in raw_hits:
                coverage = matched / usable_count
                # 覆盖率分支必须配 matched>=2：极短查询（可用词只有 1~2 个）下
                # 命中 1 个词就 coverage=1.0，会把无关查询放行。
                if (
                    matched >= min_terms
                    or score >= floor
                    or (matched >= 2 and coverage >= min_coverage)
                ):
                    local_hits.append((chunk, score))
                else:
                    gated += 1
            if gated:
                result.notes.append(
                    f"相关性闸门过滤 {gated} 条弱命中"
                    f"（matched<{min_terms} 且 score<{floor} 且 coverage<{min_coverage}）"
                )
            result.sources_used.append("local_bm25")

        remote_hits: list[RetrievedChunk] = []
        if self.client is not None and self.settings.qianfan_kb_configured:
            kb_ids = [self.settings.kb_id_for(name) for name in (domains or list(KB_IDS))]
            kb_ids = [kb for kb in kb_ids if kb]
            try:
                remote_hits = await self.client.retrieve_knowledge(normalized, kb_ids, top_k=top_k)
                if remote_hits:
                    result.sources_used.append("qianfan_kb")
            except CareFlowError as exc:
                result.degraded = True
                result.notes.append(f"千帆知识库检索不可用，已降级为本地检索：{exc.code.value}")
                log_event(
                    logger,
                    "qianfan kb retrieval failed",
                    operation="kb_retrieve",
                    provider="qianfan",
                    success=False,
                    error_code=exc.code.value,
                )
            except Exception as exc:  # noqa: BLE001
                result.degraded = True
                result.notes.append(f"千帆知识库检索异常，已降级：{type(exc).__name__}")
        elif self.client is not None and not self.settings.qianfan_kb_configured:
            if self.settings.is_qianfan:
                result.notes.append("未配置 QIANFAN_KB_*_ID，使用本地切片检索")

        merged = self._merge(local_hits, remote_hits)
        merged = self._dedupe(merged, result)
        merged = self._apply_authority(merged)

        threshold = self.settings.rag_score_threshold if min_score is None else min_score
        if threshold > 0:
            merged = [
                hit for hit in merged if float(hit.get("_score", 0.0)) >= threshold
            ]

        merged.sort(key=lambda item: item["_score"], reverse=True)
        result.best_score = float(merged[0]["_score"]) if merged else 0.0
        result.hits = [self._to_chunk(item) for item in merged[:top_k]]
        return result

    # ------------------------------------------------------------------ 内部
    def _merge(
        self,
        local_hits: list[tuple[Chunk, float]],
        remote_hits: list[RetrievedChunk],
    ) -> list[dict[str, Any]]:
        """RRF（Reciprocal Rank Fusion）融合本地与千帆结果。"""
        merged: dict[str, dict[str, Any]] = {}
        for rank, (chunk, score) in enumerate(local_hits[:60]):
            key = chunk.chunk_id
            entry = merged.setdefault(key, {"chunk": chunk, "_score": 0.0, "_local": 0.0, "_remote": 0.0})
            entry["_score"] += 1.0 / (60 + rank + 1) + score * 0.02
            entry["_local"] = score
        for rank, hit in enumerate(remote_hits):
            key = hit.chunk_id or f"QF-{rank}"
            entry = merged.get(key)
            if entry is None:
                merged[key] = {
                    "chunk": None,
                    "remote": hit,
                    "_score": 1.0 / (60 + rank + 1),
                    "_local": 0.0,
                    "_remote": hit.score,
                }
            else:
                entry["_score"] += 1.0 / (60 + rank + 1)
                entry["_remote"] = hit.score
        return list(merged.values())

    def _dedupe(self, items: list[dict[str, Any]], result: RetrievalResult) -> list[dict[str, Any]]:
        seen_fingerprint: dict[str, str] = {}
        kept: list[dict[str, Any]] = []
        for item in items:
            chunk: Chunk | None = item.get("chunk")
            remote: RetrievedChunk | None = item.get("remote")
            content = chunk.content if chunk is not None else (remote.content if remote else "")
            fingerprint = re.sub(r"\s+", "", content)[:120]
            if not fingerprint:
                continue
            previous = seen_fingerprint.get(fingerprint)
            if previous is not None:
                result.dropped.append(
                    {"reason": "duplicate_content", "chunk_id": (chunk.chunk_id if chunk else "")}
                )
                continue
            seen_fingerprint[fingerprint] = chunk.chunk_id if chunk else ""
            kept.append(item)
        return kept

    def _apply_authority(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for item in items:
            chunk: Chunk | None = item.get("chunk")
            level = ""
            if chunk is not None:
                level = chunk.authority_level
            else:
                remote = item.get("remote")
                level = remote.authority_level if remote else ""
            item["_score"] = float(item["_score"]) * AUTHORITY_BOOST.get(level, 1.0)
        return items

    @staticmethod
    def _to_chunk(item: dict[str, Any]) -> RetrievedChunk:
        chunk: Chunk | None = item.get("chunk")
        if chunk is not None:
            return RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=chunk.title,
                section=chunk.section,
                section_path=chunk.section_path,
                authority=chunk.authority,
                authority_level=chunk.authority_level,
                version=chunk.version,
                effective_date=chunk.effective_date,
                source_url=chunk.source_url,
                score=round(float(item.get("_score", 0.0)), 6),
                retrieval_source="local_bm25",
                content=chunk.content,
            )
        remote: RetrievedChunk = item["remote"]
        remote.score = round(float(item.get("_score", remote.score)), 6)
        remote.retrieval_source = "qianfan_kb"
        return remote

    # -------------------------------------------------------------- 上下文构建
    def build_context(
        self,
        hits: list[RetrievedChunk],
        *,
        max_chars: int | None = None,
        max_chars_per_chunk: int = 1600,
    ) -> tuple[str, int]:
        """把命中片段拼成带编号的上下文块。

        编号 `[n]` 与 `hits[n-1]` 严格一一对应，供 CitationService 回溯。
        """
        limit = max_chars or self.settings.rag_max_context_chars
        blocks: list[str] = []
        used = 0
        for index, hit in enumerate(hits, start=1):
            content = hit.content[:max_chars_per_chunk]
            block = (
                f"[{index}] document_id={hit.document_id} chunk_id={hit.chunk_id}\n"
                f"标题：{hit.title}\n"
                f"章节：{hit.section}\n"
                f"权威等级：{hit.authority_level or '未标注'}｜发布机构：{hit.authority or '未标注'}"
                f"｜版本：{hit.version or '未标注'}\n"
                f"来源：{hit.source_url}\n"
                f"正文：{content}\n"
            )
            if used + len(block) > limit and blocks:
                break
            blocks.append(block)
            used += len(block)
        return "\n".join(blocks), used


def authority_sort_key(level: str) -> int:
    return AUTHORITY_RANK.get(level, 99)
