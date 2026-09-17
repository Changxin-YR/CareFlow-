"""真实知识库集成测试。

只在 `knowledge/manifest/knowledge_manifest.csv` 与
`knowledge/chunks/chunks.jsonl` 都存在时运行；否则 skip。

它验证的是**真实产物**：
* manifest 能加载且没有词表/状态类问题；
* chunks 与 manifest 的 document_id 一致；
* status != active 的文档不进索引；
* 端到端 RAG 能给出**可回溯到 manifest 的**真实 Citation；
* 无证据问题不会被编造答案。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import PROJECT_ROOT, load_settings, reload_settings
from app.api import deps

MANIFEST = PROJECT_ROOT / "knowledge" / "manifest" / "knowledge_manifest.csv"
CHUNKS = PROJECT_ROOT / "knowledge" / "chunks" / "chunks.jsonl"

pytestmark = pytest.mark.skipif(
    not (MANIFEST.exists() and CHUNKS.exists()),
    reason="真实知识库产物不存在（需要先运行 knowledge 管线脚本）",
)


@pytest.fixture(scope="module")
def real_client(monkeypatch_module=None):
    import os

    os.environ["AI_PROVIDER"] = "mock"
    os.environ["APP_ENV"] = "test"
    os.environ.pop("MANIFEST_PATH", None)
    os.environ.pop("CHUNKS_PATH", None)
    reload_settings()
    deps.reset_services()
    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client
    deps.reset_services()
    reload_settings()


def _manifest_rows() -> list[dict[str, str]]:
    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _chunks() -> list[dict]:
    rows: list[dict] = []
    with CHUNKS.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def test_manifest_columns_exact():
    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as handle:
        fieldnames = csv.DictReader(handle).fieldnames
    expected = [
        "document_id", "title", "authority", "authority_level", "document_type", "version",
        "publish_date", "effective_date", "replaced_by", "status", "diseases", "scenarios",
        "language", "source_url", "local_file", "sha256", "qianfan_kb", "notes",
    ]
    assert fieldnames == expected


def test_manifest_ids_unique_and_status_valid():
    rows = _manifest_rows()
    ids = [row["document_id"] for row in rows]
    assert len(ids) == len(set(ids))
    for row in rows:
        assert row["status"] in {"active", "superseded", "draft", "disabled"}
        assert row["authority_level"] in {"P0", "P1", "P2", "P3", "P4"}
        assert row["source_url"].startswith("http")
        assert row["title"].strip()


def test_active_rows_have_files_and_sha256():
    import hashlib

    for row in _manifest_rows():
        if row["status"] != "active":
            continue
        path = PROJECT_ROOT / row["local_file"]
        assert path.exists(), f"{row['document_id']} 的 local_file 不存在：{path}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == row["sha256"], f"{row['document_id']} sha256 不一致"


def test_chunks_reference_known_documents():
    known = {row["document_id"] for row in _manifest_rows()}
    for chunk in _chunks():
        assert chunk["document_id"] in known, chunk["document_id"]
        assert chunk["chunk_id"].startswith(chunk["document_id"])
        assert chunk["content"].strip()


def test_chunk_ids_unique():
    ids = [chunk["chunk_id"] for chunk in _chunks()]
    assert len(ids) == len(set(ids))


def test_chunk_metadata_matches_manifest():
    by_id = {row["document_id"]: row for row in _manifest_rows()}
    for chunk in _chunks():
        row = by_id[chunk["document_id"]]
        assert chunk["authority_level"] == row["authority_level"]
        assert chunk["source_url"] == row["source_url"]


def test_no_inactive_document_chunks_in_index(real_client):
    store = deps.get_services().store
    inactive = {
        row["document_id"] for row in _manifest_rows() if row["status"] != "active"
    }
    indexed_docs = {chunk.document_id for chunk in store.chunks}
    assert not (indexed_docs & inactive)


def test_health_reports_real_knowledge(real_client):
    payload = real_client.get("/health").json()
    assert payload["manifest"] == "ok"
    assert payload["knowledge"] == "ok"
    assert payload["detail"]["chunks_total"] > 0


def test_real_rag_returns_verifiable_citations(real_client):
    response = real_client.post(
        "/v1/rag/answer", json={"query": "高血压患者平时吃盐要注意什么？"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    if data["insufficient_evidence"]:
        pytest.skip("真实知识库未命中该问题（可能相关文档未下载）")
    assert data["citations"]
    by_id = {row["document_id"]: row for row in _manifest_rows()}
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in _chunks()}
    for citation in data["citations"]:
        row = by_id[citation["document_id"]]
        assert row["status"] == "active"
        assert citation["source_url"] == row["source_url"]
        chunk = chunks_by_id[citation["chunk_id"]]
        assert chunk["content"].startswith(citation["quote"][:40])


def test_real_no_evidence_is_honest(real_client):
    data = real_client.post(
        "/v1/rag/answer", json={"query": "今天天气怎么样，适合去钓鱼吗"}
    ).json()["data"]
    assert data["insufficient_evidence"] is True
    assert data["citations"] == []


def test_real_followup_gives_citations(real_client):
    data = real_client.post(
        "/v1/followup/draft", json={"checkin_text": "血压158/96，最近吃盐比较多"}
    ).json()["data"]
    assert data["requires_human_confirmation"] is True
    assert data["questions"]
    if data["citations"]:
        by_id = {row["document_id"]: row for row in _manifest_rows()}
        for citation in data["citations"]:
            assert by_id[citation["document_id"]]["status"] == "active"
