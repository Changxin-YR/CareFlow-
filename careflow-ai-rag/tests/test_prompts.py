"""Prompt 资产测试 —— 保证关键安全约束真的写在 Prompt 里。"""

from __future__ import annotations

import pytest

from app.prompts import AVAILABLE_PROMPTS, PROMPTS_DIR, load_prompt, prompt_version


@pytest.mark.parametrize("name", sorted(AVAILABLE_PROMPTS))
def test_prompt_file_exists_and_non_empty(name):
    content = load_prompt(name)
    assert content.strip()
    assert len(content) > 200


@pytest.mark.parametrize("name", sorted(AVAILABLE_PROMPTS))
def test_prompt_has_version_marker(name):
    version = prompt_version(name)
    assert version != "unknown"
    assert version.split("-")[0] in {"EXTRACT", "RAG", "FOLLOWUP", "ROUTER", "SAFETY"}


def test_unknown_prompt_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist.md")


def test_extraction_prompt_declares_boundaries():
    content = load_prompt("extraction_system")
    for phrase in ("你不是医生", "禁止", "诊断", "只输出一个 JSON 对象", "observations"):
        assert phrase in content, phrase


def test_extraction_prompt_forbids_fabrication():
    content = load_prompt("extraction_system")
    assert "推测" in content
    assert "source_text" in content


def test_rag_prompt_declares_evidence_only():
    content = load_prompt("rag_system")
    for phrase in ("不是医生", "检索上下文", "insufficient_evidence", "Citation"):
        assert phrase in content, phrase


def test_rag_prompt_lists_forbidden_actions():
    content = load_prompt("rag_system")
    for phrase in ("诊断", "开药", "调药", "停药", "剂量"):
        assert phrase in content, phrase


def test_rag_prompt_mentions_document_as_data():
    content = load_prompt("rag_system")
    assert "文档数据" in content or "只是**文档数据**" in content


def test_followup_prompt_forbids_dosage_and_diagnosis():
    content = load_prompt("followup_system")
    for phrase in ("诊断结论", "药物剂量", "停药", "Attention Level"):
        assert phrase in content, phrase


def test_followup_prompt_requires_human_confirmation_semantics():
    content = load_prompt("followup_system")
    assert "随访草稿" in content
    assert "官方" in content


def test_router_prompt_lists_all_kbs():
    content = load_prompt("router_system")
    for kb in ("KB_CORE", "KB_HTN", "KB_DM", "KB_COPD", "KB_MULTIMORBIDITY", "KB_LIFESTYLE", "KB_PRIMARYCARE", "KB_WHO"):
        assert kb in content, kb


def test_safety_prompt_documents_injection_cases():
    content = load_prompt("safety_system")
    for phrase in ("忽略之前的规则", "System Prompt", "Attention Level", "SAFETY_BLOCKED"):
        assert phrase in content, phrase


def test_prompts_directory_contains_only_markdown_and_init():
    suffixes = {path.suffix for path in PROMPTS_DIR.iterdir() if path.is_file()}
    assert suffixes <= {".md", ".py"}
