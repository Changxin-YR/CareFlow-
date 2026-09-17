"""publish_date 的贯通性回归测试。

交接文档 §14 要求 Chunk Metadata 含 `publish_date`。原实现的 chunk/RetrievedChunk/
Citation 只有 `effective_date`，「发布日期」在检索与引用链路上丢失。
本文件锁定它从 manifest → chunk → RetrievedChunk → Citation 的完整透传。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT
from app.schemas.common import Citation, RetrievedChunk
from app.services.citation_service import CitationService


# --------------------------------------------------------------------------- #
# Schema 层
# --------------------------------------------------------------------------- #
def test_retrieved_chunk_has_publish_date_field():
    hit = RetrievedChunk(chunk_id="c", document_id="d")
    assert hit.publish_date == ""
    assert RetrievedChunk(chunk_id="c", document_id="d", publish_date="2024-07-01").publish_date == "2024-07-01"


def test_citation_has_publish_date_field():
    citation = Citation(
        document_id="HTN001",
        chunk_id="HTN001-0001",
        title="t",
        source_url="https://example.invalid/x",
        publish_date="2025-09-30",
    )
    assert citation.publish_date == "2025-09-30"


# --------------------------------------------------------------------------- #
# CitationService：以 manifest 为准
# --------------------------------------------------------------------------- #
def test_citation_service_copies_publish_date_from_manifest(services):
    store = services.store
    entry = store.get("HTN001")
    assert entry is not None
    # 夹具 manifest 的 publish_date 是 2025-01-01
    hit = RetrievedChunk(
        chunk_id="HTN001-0001",
        document_id="HTN001",
        title=entry.title,
        content="内容",
    )
    result = CitationService(store).build([hit])
    assert result.citations
    assert result.citations[0].publish_date == entry.publish_date


def test_citation_publish_date_ignores_llm_supplied_value(services):
    """即使检索结果里带了伪造的 publish_date，输出也必须用 manifest 的值。"""
    store = services.store
    entry = store.get("HTN001")
    hit = RetrievedChunk(
        chunk_id="HTN001-0001",
        document_id="HTN001",
        content="内容",
        publish_date="1900-01-01",  # 伪造
    )
    citation = CitationService(store).build([hit]).citations[0]
    assert citation.publish_date == entry.publish_date
    assert citation.publish_date != "1900-01-01"


# --------------------------------------------------------------------------- #
# 真实产物层
# --------------------------------------------------------------------------- #
CHUNKS = PROJECT_ROOT / "knowledge" / "chunks" / "chunks.jsonl"

pytestmark_live = pytest.mark.skipif(
    not CHUNKS.exists(), reason="真实知识库产物不存在"
)


@pytestmark_live
def test_real_chunks_carry_publish_date():
    rows = [
        json.loads(line)
        for line in CHUNKS.open(encoding="utf-8")
        if line.strip()
    ]
    assert rows
    missing = [c["chunk_id"] for c in rows if "publish_date" not in c]
    assert not missing, f"以下切片缺少 publish_date 字段：{missing[:5]}"
    # 3 篇付费墙文档没有切片；其余文档的切片都应带非空 publish_date
    empty = [
        c["chunk_id"]
        for c in rows
        if not c.get("publish_date") and c["document_id"] not in {"HTN002", "WHO001", "WHO002", "WHO003"}
    ]
    # 允许个别确实查不到发布日期的文档为空，但不应大面积缺失
    assert len(empty) <= len(rows) * 0.1, f"publish_date 为空的切片过多：{len(empty)}/{len(rows)}"


@pytestmark_live
def test_real_manifest_has_publish_date_for_most_docs():
    import csv

    manifest = PROJECT_ROOT / "knowledge" / "manifest" / "knowledge_manifest.csv"
    rows = list(csv.DictReader(manifest.open(encoding="utf-8-sig")))
    filled = [r for r in rows if r["publish_date"].strip()]
    assert len(filled) >= 28, f"只有 {len(filled)}/{len(rows)} 篇有 publish_date"
    # 本轮明确补齐的 7 条
    expected = {
        "HTN002": "2025-09-24",
        "DM002": "2021-04-27",
        "DM003": "2022-03-01",
        "MULTI001": "2023-07-24",
        "WHO001": "2020-09-07",
        "WHO002": "2020-07-13",
        "WHO003": "2018-05-02",
    }
    by_id = {r["document_id"]: r for r in rows}
    for doc_id, date in expected.items():
        assert by_id[doc_id]["publish_date"] == date, doc_id
