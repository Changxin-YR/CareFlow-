"""LLM 路径测试 —— 用可编程 MockLLMClient 驱动 qianfan 分支。

覆盖 RagService / FollowUpService 在 `AI_PROVIDER=qianfan` 下的：
正常返回、非法 JSON、超时、grounding 拦截、降级行为。
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from app.clients.mock import MockLLMClient
from app.core.config import load_settings
from app.core.errors import QianfanRateLimitError, QianfanTimeoutError
from app.schemas.followup import FollowUpRequest
from app.schemas.rag import RagRequest
from app.services.citation_service import CitationService
from app.services.followup_service import FollowUpService
from app.services.rag_service import RagService
from app.services.retrieval_service import RetrievalService
from app.services.safety_service import SafetyService


def _llm_settings(**overrides):
    return dataclasses.replace(
        load_settings(),
        ai_provider="qianfan",
        qianfan_api_key="test-key",
        qianfan_app_id="test-app",
        **overrides,
    )


def _build(services, handler, **overrides):
    settings = _llm_settings(**overrides)
    client = MockLLMClient(handler=handler)
    safety = SafetyService()
    citation = CitationService(services.store)
    retrieval = RetrievalService(services.store, client, settings)
    rag = RagService(
        services.store,
        client,
        settings=settings,
        safety=safety,
        citation_service=citation,
        retrieval_service=retrieval,
    )
    followup = FollowUpService(
        services.store,
        client,
        settings=settings,
        safety=safety,
        citation_service=citation,
        retrieval_service=retrieval,
    )
    return rag, followup, client


def _rag_handler(answer: str, chunk_ids: list[str] | None = None, insufficient: bool = False):
    def handler(task: str, messages: list) -> str:
        return json.dumps(
            {
                "answer": answer,
                "insufficient_evidence": insufficient,
                "used_chunk_ids": chunk_ids or [],
            },
            ensure_ascii=False,
        )

    return handler


# --------------------------------------------------------------------------- #
# RAG
# --------------------------------------------------------------------------- #
async def test_rag_llm_answer_used_and_cited(services):
    rag, _, client = _build(
        services,
        _rag_handler("家庭血压测量建议静坐五分钟（见 [1]）。", chunk_ids=["HTN001-0001"]),
    )
    data = await rag.answer(RagRequest(query="家庭血压应该怎么测量？"))
    assert data.insufficient_evidence is False
    assert data.answer.strip()
    assert data.citations
    assert data.citations[0].document_id == "HTN001"
    assert client.calls[0]["task"] == "rag_answer"
    assert data.model.provider == "mock"  # MockLLMClient 自报 provider=mock


async def test_rag_llm_insufficient_evidence_clears_citations(services):
    rag, _, _ = _build(services, _rag_handler("没有找到依据。", insufficient=True))
    data = await rag.answer(RagRequest(query="家庭血压应该怎么测量？"))
    assert data.insufficient_evidence is True
    assert data.citations == []


async def test_rag_llm_invalid_json_falls_back_to_extract(services):
    rag, _, _ = _build(services, lambda task, messages: "我无法输出 JSON")
    data = await rag.answer(RagRequest(query="家庭血压应该怎么测量？"))
    assert "摘录" in data.answer
    assert getattr(data, "_degraded") is True
    assert any("非法 JSON" in note for note in getattr(data, "_notes"))


async def test_rag_llm_timeout_falls_back_to_extract(services):
    settings = _llm_settings()
    client = MockLLMClient(responses=[QianfanTimeoutError("超时")])
    safety = SafetyService()
    citation = CitationService(services.store)
    retrieval = RetrievalService(services.store, client, settings)
    rag = RagService(
        services.store, client, settings=settings, safety=safety,
        citation_service=citation, retrieval_service=retrieval,
    )
    data = await rag.answer(RagRequest(query="家庭血压应该怎么测量？"))
    assert "摘录" in data.answer
    assert getattr(data, "_degraded") is True
    assert data.citations


async def test_rag_llm_rate_limit_falls_back(services):
    settings = _llm_settings()
    client = MockLLMClient(responses=[QianfanRateLimitError("限流")])
    safety = SafetyService()
    citation = CitationService(services.store)
    retrieval = RetrievalService(services.store, client, settings)
    rag = RagService(
        services.store, client, settings=settings, safety=safety,
        citation_service=citation, retrieval_service=retrieval,
    )
    data = await rag.answer(RagRequest(query="家庭血压应该怎么测量？"))
    assert getattr(data, "_degraded") is True
    assert "摘录" in data.answer


async def test_rag_llm_invented_chunk_id_is_dropped(services):
    rag, _, _ = _build(
        services, _rag_handler("答案内容（见 [1]）。", chunk_ids=["FAKE-9999"])
    )
    data = await rag.answer(RagRequest(query="家庭血压应该怎么测量？"))
    assert any(item.reason == "chunk_not_retrieved_this_round" for item in data.dropped_citations)


async def test_rag_llm_dosage_output_is_redacted(services):
    rag, _, _ = _build(
        services,
        _rag_handler("建议每天服用 20mg 硝苯地平（见 [1]）。"),
    )
    data = await rag.answer(RagRequest(query="家庭血压应该怎么测量？"))
    assert "20mg" not in data.answer
    assert "BLOCKED_DOSAGE_RECOMMENDATION" in data.safety.flags


async def test_rag_llm_diagnosis_output_is_redacted(services):
    rag, _, _ = _build(services, _rag_handler("你患有高血压（见 [1]）。请注意监测。"))
    data = await rag.answer(RagRequest(query="家庭血压应该怎么测量？"))
    assert "你患有" not in data.answer
    assert "BLOCKED_DIAGNOSIS_STATEMENT" in data.safety.flags


async def test_rag_llm_router_used_for_unmatched_query(services):
    def handler(task: str, messages: list) -> str:
        if task == "route":
            return json.dumps({"domains": ["KB_HTN"], "reason": "x"})
        return json.dumps(
            {"answer": "以下内容（见 [1]）。", "insufficient_evidence": False, "used_chunk_ids": []},
            ensure_ascii=False,
        )

    rag, _, client = _build(services, handler)
    data = await rag.answer(RagRequest(query="那个测出来 158 要不要紧"))
    tasks = [call["task"] for call in client.calls]
    assert "route" in tasks
    assert data.domains


# --------------------------------------------------------------------------- #
# FollowUp
# --------------------------------------------------------------------------- #
def _followup_handler(summary: str, questions: list[str], education: str, chunk_ids=None):
    def handler(task: str, messages: list) -> str:
        return json.dumps(
            {
                "summary": summary,
                "questions": questions,
                "education": education,
                "used_chunk_ids": chunk_ids or [],
            },
            ensure_ascii=False,
        )

    return handler


async def test_followup_llm_draft_used(services):
    _, followup, client = _build(
        services,
        _followup_handler(
            "本次随访记录了血压情况。",
            ["最近血压测量是否规律"],
            "生活方式干预是高血压管理的基础（见 [1]）。",
            ["HTN001-0002"],
        ),
    )
    data = await followup.draft(FollowUpRequest(checkin_text="血压158/96"))
    assert data.summary.startswith("本次随访记录了血压情况")
    assert data.questions == ["最近血压测量是否规律？"]
    assert data.citations
    assert client.calls[0]["task"] == "followup"
    assert data.requires_human_confirmation is True


async def test_followup_llm_hallucinated_summary_rejected(services):
    _, followup, _ = _build(
        services,
        _followup_handler(
            "患者血压 999/88，心率 200。",  # 原文中不存在这些数字
            ["问题一"],
            "教育内容（见 [1]）。",
            [],
        ),
    )
    data = await followup.draft(FollowUpRequest(checkin_text="血压158/96，最近有点头晕"))
    assert "999" not in data.summary
    assert "HALLUCINATED_SUMMARY_BLOCKED" in data.safety.flags


async def test_followup_llm_grounded_summary_accepted(services):
    _, followup, _ = _build(
        services,
        _followup_handler("本次记录血压 158/96。", ["问题一"], "教育（见 [1]）。", []),
    )
    data = await followup.draft(FollowUpRequest(checkin_text="血压158/96，最近有点头晕"))
    assert "158/96" in data.summary


async def test_followup_llm_invalid_json_falls_back(services):
    _, followup, _ = _build(services, lambda task, messages: "不是 JSON")
    data = await followup.draft(FollowUpRequest(checkin_text="血压158/96，有点头晕"))
    assert data.summary
    assert data.questions
    assert getattr(data, "_degraded") is True


async def test_followup_llm_timeout_falls_back(services):
    settings = _llm_settings()
    client = MockLLMClient(responses=[QianfanTimeoutError("超时")])
    safety = SafetyService()
    citation = CitationService(services.store)
    retrieval = RetrievalService(services.store, client, settings)
    followup = FollowUpService(
        services.store, client, settings=settings, safety=safety,
        citation_service=citation, retrieval_service=retrieval,
    )
    data = await followup.draft(FollowUpRequest(checkin_text="血压158/96"))
    assert data.summary
    assert getattr(data, "_degraded") is True


async def test_followup_llm_question_normalisation(services):
    _, followup, _ = _build(
        services,
        _followup_handler("摘要", ["没有问号的句子", "   ", "有问号的句子？"], "教育"),
    )
    data = await followup.draft(FollowUpRequest(checkin_text="血压158/96"))
    assert data.questions == ["没有问号的句子？", "有问号的句子？"]


async def test_followup_include_education_false(services):
    _, followup, _ = _build(
        services,
        _followup_handler("摘要", ["问题？"], "教育内容（见 [1]）。"),
    )
    data = await followup.draft(
        FollowUpRequest(checkin_text="血压158/96", options={"include_education": False})
    )
    assert data.education == ""
    assert data.citations == []


async def test_followup_no_hits_skips_llm(services):
    """无检索命中时不应该调用 LLM 生成草稿（省钱且避免无依据生成）。

    注意：Domain Router 仍可能被调用（它只决定去哪些知识库检索），
    但 `followup` 与 `extract` 任务必须被跳过。
    """
    _, followup, client = _build(services, _followup_handler("摘要", ["问题？"], "教育"))
    data = await followup.draft(FollowUpRequest(checkin_text="今天天气不错适合钓鱼"))
    tasks = [call["task"] for call in client.calls]
    assert "followup" not in tasks
    assert "extract" not in tasks
    assert "未检索到" in data.education
    assert data.citations == []


@pytest.mark.parametrize("note_keyword", ["非法 JSON", "QIANFAN"])
async def test_followup_degraded_notes_recorded(services, note_keyword):
    if note_keyword == "非法 JSON":
        _, followup, _ = _build(services, lambda task, messages: "oops")
    else:
        settings = _llm_settings()
        client = MockLLMClient(responses=[QianfanTimeoutError("超时")])
        safety = SafetyService()
        citation = CitationService(services.store)
        retrieval = RetrievalService(services.store, client, settings)
        followup = FollowUpService(
            services.store, client, settings=settings, safety=safety,
            citation_service=citation, retrieval_service=retrieval,
        )
    data = await followup.draft(FollowUpRequest(checkin_text="血压158/96"))
    assert any(note_keyword in note for note in getattr(data, "_notes"))
