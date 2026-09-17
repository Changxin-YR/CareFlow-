"""Knowledge Manifest / 切片索引 单元测试。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.api import deps
from app.core.config import MANIFEST_COLUMNS, reload_settings
from app.services.manifest_service import Chunk, KnowledgeStore


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MANIFEST_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in MANIFEST_COLUMNS})


def test_manifest_loaded(services):
    store = services.store
    assert store.manifest_loaded is True
    assert store.manifest_error == ""
    assert len(store.entries) == 5
    assert store.get("HTN001").title.startswith("【测试夹具】")


def test_only_active_documents_are_indexed(services):
    store = services.store
    # 已作废文档的切片必须被排除在检索索引之外
    assert "COPD900-0001" not in store.chunks_by_id
    assert "HTN001-0001" in store.chunks_by_id
    assert len(store.chunks) == 4


def test_chunks_grouped_by_document(services):
    store = services.store
    assert len(store.chunks_by_document["HTN001"]) == 2
    assert store.get_chunk("HTN001-0002").section == "二、生活方式干预"


def test_stats_and_health(services):
    stats = services.store.stats()
    assert stats["documents_total"] == 5
    assert stats["documents_active"] == 4
    assert stats["chunks_total"] == 4
    assert stats["documents_by_status"]["superseded"] == 1
    health = services.store.health()
    assert health["manifest"] == "ok"
    assert health["knowledge"] == "ok"
    assert health["problems"] == []


def test_active_documents_and_domain_filter(services):
    store = services.store
    assert {entry.document_id for entry in store.active_documents()} == {
        "HTN001",
        "DM001",
        "LIFE001",
        "COPD901",
    }
    assert store.documents_for_domains(["KB_HTN"]) == {"HTN001"}
    assert "DM001" in store.documents_for_domains(["DIABETES"])
    # 不带域时返回**全部 active** 文档；域过滤也不应把 draft/superseded 混进来
    assert store.documents_for_domains([]) == {
        "HTN001", "DM001", "LIFE001", "COPD901"
    }
    assert "COPD900" not in store.documents_for_domains(["KB_COPD"])
    assert store.documents_for_domains(["KB_COPD"]) == {"COPD901"}
    # 域里没有任何 active 文档 → 空集合（调用方据此判定"无证据"，而不是放大到全库）
    assert store.documents_for_domains(["KB_DOES_NOT_EXIST"]) == set()


def test_missing_manifest_reports_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("MANIFEST_PATH", str(tmp_path / "nope.csv"))
    monkeypatch.setenv("CHUNKS_PATH", str(tmp_path / "nope.jsonl"))
    reload_settings()
    from app.core.config import load_settings

    store = KnowledgeStore(load_settings()).load()
    health = store.health()
    assert store.manifest_loaded is False
    assert health["manifest"] == "missing"
    assert health["knowledge"] == "missing"
    assert "不存在" in store.manifest_error


def test_missing_required_column_is_fatal(tmp_path):
    from app.core.config import load_settings

    manifest = tmp_path / "bad.csv"
    manifest.write_text("document_id,title\nX1,只有两列\n", encoding="utf-8")
    monkeypatch_settings(tmp_path, manifest)
    store = KnowledgeStore(load_settings()).load()
    assert store.manifest_loaded is False
    assert "缺少列" in store.manifest_error


def monkeypatch_settings(tmp_path: Path, manifest: Path) -> None:
    import os

    os.environ["MANIFEST_PATH"] = str(manifest)
    os.environ["CHUNKS_PATH"] = str(tmp_path / "none.jsonl")
    reload_settings()


def test_duplicate_and_invalid_vocab_problems(tmp_path, monkeypatch):
    manifest = tmp_path / "dup.csv"
    base = {
        "document_id": "X1",
        "title": "T",
        "authority": "A",
        "authority_level": "P1",
        "document_type": "nhc_policy",
        "version": "2024",
        "status": "active",
        "diseases": "NOT_A_DISEASE",
        "scenarios": "education",
        "source_url": "https://example.invalid/x1",
        "local_file": "PENDING",
        "qianfan_kb": "KB_NOT_EXIST",
    }
    _write_manifest(manifest, [base, dict(base), dict(base, document_id="X2", authority_level="P9", status="weird")])
    monkeypatch.setenv("MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("CHUNKS_PATH", str(tmp_path / "none.jsonl"))
    reload_settings()
    from app.core.config import load_settings

    store = KnowledgeStore(load_settings()).load()
    joined = " | ".join(store.problems)
    assert "重复" in joined
    assert "NOT_A_DISEASE" in joined
    assert "KB_NOT_EXIST" in joined
    assert "P9" in joined
    assert "weird" in joined
    assert store.health()["manifest"] == "degraded"


def test_chunk_from_dict_tolerates_missing_fields():
    chunk = Chunk.from_dict({"chunk_id": "A-1", "document_id": "A", "content": "文本"})
    assert chunk.char_count == 2
    assert chunk.diseases == []
    assert chunk.section_path == []


def test_chunks_jsonl_bad_lines_are_recorded(tmp_path, monkeypatch, knowledge_dir):
    bad = tmp_path / "bad_chunks.jsonl"
    bad.write_text('{"chunk_id":"A-1","document_id":"HTN001","content":"x"}\nNOT JSON\n', encoding="utf-8")
    monkeypatch.setenv("MANIFEST_PATH", str(knowledge_dir["manifest"]))
    monkeypatch.setenv("CHUNKS_PATH", str(bad))
    reload_settings()
    from app.core.config import load_settings

    store = KnowledgeStore(load_settings()).load()
    assert any("非法 JSON" in problem for problem in store.problems)
    assert len(store.chunks) == 1


def test_knowledge_store_requires_ready(services):
    services.store.require_ready()  # 不应抛异常


@pytest.mark.parametrize("kb_name", ["KB_CORE", "KB_HTN", "KB_DM", "KB_COPD"])
def test_kb_id_lookup(services, kb_name):
    value = services.settings.kb_id_for(kb_name)
    assert isinstance(value, str)


def test_deps_build_services_uses_env(mock_env):
    deps.reset_services()
    services = deps.build_services()
    assert services.settings.ai_provider == "mock"
    assert services.store.manifest_loaded is True
    assert json.dumps(services.settings.redacted(), ensure_ascii=False).find("api_key") >= 0
