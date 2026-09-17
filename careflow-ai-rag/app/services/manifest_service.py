"""Knowledge Manifest 与本地切片索引的加载 / 查询 / 校验。

数据来源（均由 `scripts/` 下的管线脚本生成）：

* ``knowledge/manifest/knowledge_manifest.csv``
* ``knowledge/chunks/chunks.jsonl``

生产检索**只使用** ``status=active`` 的文档。任何 Citation 都必须能在
manifest 中找到对应的 active 文档，否则判定为幻觉引用并丢弃。
"""

from __future__ import annotations

import csv
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import (
    AUTHORITY_LEVELS,
    AUTHORITY_RANK,
    DISEASE_VOCAB,
    DOCUMENT_STATUSES,
    KB_IDS,
    MANIFEST_COLUMNS,
    SCENARIO_VOCAB,
    Settings,
    load_settings,
)
from app.core.errors import ManifestInvalidError
from app.core.logging_config import get_logger

logger = get_logger("services.manifest")

PENDING_SENTINEL = "PENDING"
DOCUMENT_TYPES = (
    "national_standard",
    "nhc_policy",
    "nhc_guideline",
    "professional_guideline",
    "expert_consensus",
    "who_guideline",
    "other",
)


def _split_tokens(raw: str) -> list[str]:
    if not raw:
        return []
    parts = [part.strip() for part in str(raw).replace("；", "|").replace(";", "|").split("|")]
    return [part for part in parts if part]


@dataclass
class ManifestEntry:
    """一行 manifest。"""

    document_id: str
    title: str = ""
    authority: str = ""
    authority_level: str = ""
    document_type: str = ""
    version: str = ""
    publish_date: str = ""
    effective_date: str = ""
    replaced_by: str = ""
    status: str = ""
    diseases: list[str] = field(default_factory=list)
    scenarios: list[str] = field(default_factory=list)
    language: str = "zh"
    source_url: str = ""
    local_file: str = ""
    sha256: str = ""
    qianfan_kb: str = ""
    notes: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_downloaded(self) -> bool:
        return bool(self.local_file) and self.local_file.upper() != PENDING_SENTINEL

    @property
    def authority_rank(self) -> int:
        return AUTHORITY_RANK.get(self.authority_level, 99)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "authority": self.authority,
            "authority_level": self.authority_level,
            "document_type": self.document_type,
            "version": self.version,
            "publish_date": self.publish_date,
            "effective_date": self.effective_date,
            "replaced_by": self.replaced_by,
            "status": self.status,
            "diseases": list(self.diseases),
            "scenarios": list(self.scenarios),
            "language": self.language,
            "source_url": self.source_url,
            "local_file": self.local_file,
            "sha256": self.sha256,
            "qianfan_kb": self.qianfan_kb,
            "notes": self.notes,
        }

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "ManifestEntry":
        return cls(
            document_id=(row.get("document_id") or "").strip(),
            title=(row.get("title") or "").strip(),
            authority=(row.get("authority") or "").strip(),
            authority_level=(row.get("authority_level") or "").strip(),
            document_type=(row.get("document_type") or "").strip(),
            version=(row.get("version") or "").strip(),
            publish_date=(row.get("publish_date") or "").strip(),
            effective_date=(row.get("effective_date") or "").strip(),
            replaced_by=(row.get("replaced_by") or "").strip(),
            status=(row.get("status") or "").strip().lower(),
            diseases=_split_tokens(row.get("diseases") or ""),
            scenarios=_split_tokens(row.get("scenarios") or ""),
            language=(row.get("language") or "zh").strip() or "zh",
            source_url=(row.get("source_url") or "").strip(),
            local_file=(row.get("local_file") or "").strip(),
            sha256=(row.get("sha256") or "").strip(),
            qianfan_kb=(row.get("qianfan_kb") or "").strip(),
            notes=(row.get("notes") or "").strip(),
        )


@dataclass
class Chunk:
    """一个知识切片。"""

    chunk_id: str
    document_id: str
    content: str
    title: str = ""
    authority: str = ""
    authority_level: str = ""
    version: str = ""
    effective_date: str = ""
    diseases: list[str] = field(default_factory=list)
    scenarios: list[str] = field(default_factory=list)
    section: str = ""
    section_path: list[str] = field(default_factory=list)
    source_url: str = ""
    char_count: int = 0
    index: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any], index: int = 0) -> "Chunk":
        content = str(payload.get("content") or "")
        return cls(
            chunk_id=str(payload.get("chunk_id") or f"UNKNOWN-{index:04d}"),
            document_id=str(payload.get("document_id") or ""),
            content=content,
            title=str(payload.get("title") or ""),
            authority=str(payload.get("authority") or ""),
            authority_level=str(payload.get("authority_level") or ""),
            version=str(payload.get("version") or ""),
            effective_date=str(payload.get("effective_date") or ""),
            diseases=[str(item) for item in (payload.get("diseases") or [])],
            scenarios=[str(item) for item in (payload.get("scenarios") or [])],
            section=str(payload.get("section") or ""),
            section_path=[str(item) for item in (payload.get("section_path") or [])],
            source_url=str(payload.get("source_url") or ""),
            char_count=int(payload.get("char_count") or len(content)),
            index=index,
        )


class KnowledgeStore:
    """manifest + chunks 的内存索引（线程安全、可热重载）。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.entries: dict[str, ManifestEntry] = {}
        self.chunks: list[Chunk] = []
        self.chunks_by_id: dict[str, Chunk] = {}
        self.chunks_by_document: dict[str, list[Chunk]] = {}
        self.problems: list[str] = []
        self.manifest_loaded = False
        self.chunks_loaded = False
        self.manifest_error = ""
        self.chunks_error = ""
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 加载
    def load(self, *, force: bool = False) -> "KnowledgeStore":
        with self._lock:
            if self.manifest_loaded and not force:
                return self
            self._load_manifest()
            self._load_chunks()
            return self

    def reload(self) -> "KnowledgeStore":
        return self.load(force=True)

    def _load_manifest(self) -> None:
        self.entries = {}
        self.problems = []
        self.manifest_error = ""
        path = Path(self.settings.manifest_path)
        if not path.exists():
            self.manifest_loaded = False
            self.manifest_error = f"manifest 不存在：{path}"
            logger.warning(self.manifest_error)
            return
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                missing = [col for col in MANIFEST_COLUMNS if col not in (reader.fieldnames or [])]
                if missing:
                    self.manifest_error = f"manifest 缺少列：{missing}"
                    self.manifest_loaded = False
                    return
                for row in reader:
                    entry = ManifestEntry.from_row(row)
                    if not entry.document_id:
                        continue
                    if entry.document_id in self.entries:
                        self.problems.append(f"document_id 重复：{entry.document_id}")
                        continue
                    self.entries[entry.document_id] = entry
            self.manifest_loaded = True
            logger.info("manifest 已加载：%d 篇文档", len(self.entries))
        except Exception as exc:  # noqa: BLE001
            self.manifest_loaded = False
            self.manifest_error = f"manifest 解析失败：{type(exc).__name__}: {exc}"
            logger.error(self.manifest_error)
        self.problems.extend(self._validate_entries())

    def _load_chunks(self) -> None:
        self.chunks = []
        self.chunks_by_id = {}
        self.chunks_by_document = {}
        self.chunks_error = ""
        path = Path(self.settings.chunks_path)
        if not path.exists():
            self.chunks_loaded = False
            self.chunks_error = f"chunks 不存在：{path}"
            logger.warning(self.chunks_error)
            return
        count = 0
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        self.problems.append(f"chunks.jsonl 第 {count + 1} 行非法 JSON")
                        continue
                    if not isinstance(payload, dict):
                        continue
                    chunk = Chunk.from_dict(payload, index=len(self.chunks))
                    count += 1
                    # 只索引 active 文档的切片 —— 生产检索禁用 superseded/draft/disabled
                    entry = self.entries.get(chunk.document_id)
                    if entry is None:
                        # document_id 不在 manifest 中：数据完整性有问题，拒绝入索引
                        if len(self.problems) < 50:
                            self.problems.append(
                                f"chunk {chunk.chunk_id} 的 document_id={chunk.document_id!r} 不在 manifest 中"
                            )
                        continue
                    if not entry.is_active:
                        continue
                    self.chunks.append(chunk)
                    self.chunks_by_id[chunk.chunk_id] = chunk
                    self.chunks_by_document.setdefault(chunk.document_id, []).append(chunk)
            self.chunks_loaded = True
            logger.info("chunks 已加载：%d 条（原始 %d 行）", len(self.chunks), count)
        except Exception as exc:  # noqa: BLE001
            self.chunks_loaded = False
            self.chunks_error = f"chunks 解析失败：{type(exc).__name__}: {exc}"
            logger.error(self.chunks_error)

    # ------------------------------------------------------------------ 校验
    def _validate_entries(self) -> list[str]:
        problems: list[str] = []
        for entry in self.entries.values():
            if entry.authority_level not in AUTHORITY_LEVELS:
                problems.append(f"{entry.document_id}: 非法 authority_level={entry.authority_level!r}")
            if entry.status not in DOCUMENT_STATUSES:
                problems.append(f"{entry.document_id}: 非法 status={entry.status!r}")
            if entry.source_url and not entry.source_url.startswith("http"):
                problems.append(f"{entry.document_id}: source_url 非法")
            if entry.qianfan_kb and entry.qianfan_kb not in KB_IDS:
                problems.append(f"{entry.document_id}: 未知 qianfan_kb={entry.qianfan_kb!r}")
            for disease in entry.diseases:
                if disease not in DISEASE_VOCAB:
                    problems.append(f"{entry.document_id}: 未知 disease token={disease!r}")
            for scenario in entry.scenarios:
                if scenario not in SCENARIO_VOCAB:
                    problems.append(f"{entry.document_id}: 未知 scenario token={scenario!r}")
        return problems

    # ------------------------------------------------------------------ 查询
    def get(self, document_id: str) -> ManifestEntry | None:
        return self.entries.get(document_id)

    def is_active(self, document_id: str) -> bool:
        entry = self.entries.get(document_id)
        return bool(entry and entry.is_active)

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        return self.chunks_by_id.get(chunk_id)

    def active_documents(self) -> list[ManifestEntry]:
        return [entry for entry in self.entries.values() if entry.is_active]

    def documents_for_domains(self, domains: list[str]) -> set[str]:
        """域 → document_id 集合。

        只返回 ``status=active`` 的文档：本方法的唯一用途是给检索做元数据过滤，
        把 draft/superseded 混进来没有意义（它们的切片本来就不在索引里），
        还会让"该域是否有可检索内容"的判断失真。
        """
        if not domains:
            return {entry.document_id for entry in self.active_documents()}
        wanted = set(domains)
        return {
            entry.document_id
            for entry in self.active_documents()
            if entry.qianfan_kb in wanted or (set(entry.diseases) & wanted)
        }

    # ------------------------------------------------------------------ 统计
    def stats(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        by_level: dict[str, int] = {}
        by_kb: dict[str, int] = {}
        for entry in self.entries.values():
            by_status[entry.status] = by_status.get(entry.status, 0) + 1
            by_level[entry.authority_level] = by_level.get(entry.authority_level, 0) + 1
            if entry.qianfan_kb:
                by_kb[entry.qianfan_kb] = by_kb.get(entry.qianfan_kb, 0) + 1
        chunks_by_kb: dict[str, int] = {}
        for chunk in self.chunks:
            entry = self.entries.get(chunk.document_id)
            kb = entry.qianfan_kb if entry else "UNKNOWN"
            chunks_by_kb[kb] = chunks_by_kb.get(kb, 0) + 1
        return {
            "documents_total": len(self.entries),
            "documents_active": len(self.active_documents()),
            "documents_by_status": by_status,
            "documents_by_authority_level": by_level,
            "documents_by_kb": by_kb,
            "chunks_total": len(self.chunks),
            "chunks_indexed_documents": len(self.chunks_by_document),
            "chunks_by_kb": chunks_by_kb,
            "manifest_path": str(self.settings.manifest_path),
            "chunks_path": str(self.settings.chunks_path),
            "problems": len(self.problems),
        }

    def health(self) -> dict[str, Any]:
        """给 /health 与 /v1/status 用的健康视图。"""
        stats = self.stats()
        manifest_status = "ok" if self.manifest_loaded and not self.problems else (
            "missing" if not self.manifest_loaded else "degraded"
        )
        if self.chunks_loaded and self.chunks:
            knowledge_status = "ok"
        elif self.chunks_loaded:
            knowledge_status = "empty"
        else:
            knowledge_status = "missing"
        return {
            "manifest": manifest_status,
            "knowledge": knowledge_status,
            "manifest_error": self.manifest_error,
            "chunks_error": self.chunks_error,
            "problems": self.problems[:20],
            "stats": stats,
        }

    def require_ready(self) -> None:
        """在需要知识库的接口里做前置断言。"""
        if not self.manifest_loaded:
            raise ManifestInvalidError(
                self.manifest_error or "Knowledge Manifest 不可用",
                details={"path": str(self.settings.manifest_path)},
            )


_store: KnowledgeStore | None = None


def get_knowledge_store(settings: Settings | None = None) -> KnowledgeStore:
    """进程级单例。"""
    global _store
    if _store is None:
        _store = KnowledgeStore(settings)
    return _store


def reset_knowledge_store() -> None:
    global _store
    _store = None
