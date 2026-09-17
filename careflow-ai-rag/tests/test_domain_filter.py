"""域过滤（Metadata Filter）回归测试。

对应真实缺陷：``RetrievalService.search`` 里写的是 ``allowed_ids or None``。
当调用方显式指定了知识域、而该域**没有任何文档**时，``documents_for_domains``
返回**空集合**，空集合是 falsy → 变成 ``None`` → **不加任何过滤 → 搜全库**。
调用方明确限定了范围，服务端却悄悄扩大，与之前修掉的 ``options.domains``
非法值静默丢弃属同一类问题。
"""

from __future__ import annotations

import dataclasses

import pytest

from app.services.retrieval_service import RetrievalService


async def test_explicit_domain_restricts_results(services):
    result = await services.retrieval.search("血压 血糖 随访 食盐", domains=["KB_DM"])
    assert result.hits
    assert {hit.document_id for hit in result.hits} == {"DM001"}


async def test_explicit_empty_domain_does_not_fall_back_to_full_corpus(services):
    """KB_WHO 在夹具里没有任何文档 → 必须判无证据，而不是搜全库。"""
    result = await services.retrieval.search("血压 血糖 随访 食盐 家庭医生", domains=["KB_WHO"])
    assert result.is_empty, f"不应放大到全库，实际命中 {[h.document_id for h in result.hits]}"
    assert any("没有任何文档" in note for note in result.notes)


async def test_no_domains_searches_whole_active_corpus(services):
    result = await services.retrieval.search("血压 血糖 随访 食盐", domains=None)
    assert result.hits
    assert len({hit.document_id for hit in result.hits}) >= 2


async def test_empty_domain_list_means_no_filter(services):
    result = await services.retrieval.search("血压 血糖 随访 食盐", domains=[])
    assert result.hits


async def test_inactive_document_never_returned_even_if_domain_matches(services):
    """COPD900 已作废，即使它属于 KB_COPD 也不能被返回。"""
    result = await services.retrieval.search("已作废 切片 慢阻肺", domains=["KB_COPD"])
    assert all(hit.document_id != "COPD900" for hit in result.hits)


def test_documents_for_domains_excludes_inactive(services):
    assert services.store.documents_for_domains(["KB_COPD"]) == {"COPD901"}


def test_documents_for_domains_empty_when_domain_unknown(services):
    assert services.store.documents_for_domains(["KB_NOPE"]) == set()


def test_retrieval_service_respects_injected_settings(services):
    strict = dataclasses.replace(
        services.settings, rag_min_matched_terms=1, rag_min_relevance_score=0.0
    )
    service = RetrievalService(services.store, None, strict)
    assert service.settings.rag_min_matched_terms == 1


def test_api_rejects_unknown_domain_before_retrieval(client):
    response = client.post(
        "/v1/rag/answer", json={"query": "高血压", "options": {"domains": ["KB_NOPE"]}}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


def test_api_explicit_empty_domain_returns_no_evidence(client):
    """KB_WHO 在夹具里没有文档 → 走 no-evidence，而不是拿别的域来答。"""
    response = client.post(
        "/v1/rag/answer", json={"query": "高血压 血糖 食盐 随访", "options": {"domains": ["KB_WHO"]}}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["insufficient_evidence"] is True
    assert data["citations"] == []
    assert data["retrieved"] == []


def test_api_domain_filter_restricts_retrieved(client):
    data = client.post(
        "/v1/rag/answer",
        json={"query": "血压 血糖 食盐 随访", "options": {"domains": ["KB_DM"]}},
    ).json()["data"]
    assert data["retrieved"]
    assert {hit["document_id"] for hit in data["retrieved"]} == {"DM001"}
