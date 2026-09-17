"""检索服务单元测试（BM25 / 去重 / 域过滤 / 相关性闸门 / 无证据）。"""

from __future__ import annotations

import pytest

from app.services.retrieval_service import (
    BM25Index,
    RetrievalService,
    normalize_query,
    query_terms,
    tokenize,
)


def test_tokenize_chinese_bigrams():
    tokens = tokenize("高血压")
    assert "高血" in tokens
    assert "血压" in tokens


def test_tokenize_ascii_and_numbers():
    tokens = tokenize("HbA1c 7.5 mmol/L")
    assert "hba1c" in tokens
    assert "7.5" in tokens
    assert "mmol/l" in tokens


def test_stop_bigrams_filtered():
    assert "怎么" not in tokenize("怎么办")
    assert "应该" not in tokenize("应该怎么做")


def test_query_terms():
    assert "血压" in query_terms(normalize_query("血压是多少"))


async def test_search_finds_relevant_chunk(services):
    result = await services.retrieval.search("家庭血压应该怎么测量")
    assert result.hits
    assert result.hits[0].document_id == "HTN001"
    assert result.hits[0].chunk_id == "HTN001-0001"
    assert result.sources_used == ["local_bm25"]
    assert result.best_score > 0


async def test_search_respects_domain_filter(services):
    result = await services.retrieval.search("血压 血糖 随访", domains=["KB_DM"])
    assert result.hits
    assert {hit.document_id for hit in result.hits} == {"DM001"}


async def test_search_excludes_superseded_document(services):
    result = await services.retrieval.search("已作废 切片 慢阻肺 随访")
    ids = {hit.document_id for hit in result.hits}
    assert "COPD900" not in ids


async def test_search_no_hits_for_unrelated_query(services):
    result = await services.retrieval.search("今天天气怎么样适合去钓鱼吗")
    assert result.is_empty
    assert result.best_score == 0.0


async def test_search_top_k_applied(services):
    result = await services.retrieval.search("血压 血糖 食盐 饮食 随访", top_k=1)
    assert len(result.hits) <= 1


async def test_min_score_filter(services):
    strict = await services.retrieval.search("血压", min_score=99.0)
    assert strict.is_empty


def test_authority_boost_ranking():
    from app.services.retrieval_service import AUTHORITY_BOOST

    assert AUTHORITY_BOOST["P0"] > AUTHORITY_BOOST["P1"] > AUTHORITY_BOOST["P2"]
    assert AUTHORITY_BOOST["P2"] >= AUTHORITY_BOOST["P3"] > AUTHORITY_BOOST["P4"]


def test_authority_boost_applied_to_equal_scores(services):
    """同分情况下，权威等级高的文档必须排在前面（权威过滤）。"""
    from app.services.manifest_service import Chunk

    def _chunk(document_id: str, level: str) -> Chunk:
        return Chunk(
            chunk_id=f"{document_id}-0001",
            document_id=document_id,
            content="同样的内容用于比较",
            authority_level=level,
        )

    items = [
        {"chunk": _chunk("LOW", "P3"), "_score": 1.0},
        {"chunk": _chunk("HIGH", "P0"), "_score": 1.0},
    ]
    boosted = services.retrieval._apply_authority(items)
    scores = {item["chunk"].document_id: item["_score"] for item in boosted}
    assert scores["HIGH"] > scores["LOW"]


def test_bm25_empty_index():
    index = BM25Index([])
    assert index.is_empty
    assert index.search("任何查询") == []


def test_bm25_index_search_returns_scored_triples(services):
    top = services.retrieval.index.search("家庭血压测量")
    assert top
    chunk, score, matched = top[0]
    assert chunk.chunk_id == "HTN001-0001"
    assert score > 0
    assert matched >= 1


def test_bm25_matched_terms_count_reported(services):
    results = {
        item[0].chunk_id: item[2]
        for item in services.retrieval.index.search("家庭血压测量 静坐")
    }
    assert results["HTN001-0001"] >= 2


async def test_relevance_gate_filters_spurious_hits(services):
    """高频二元组（今天/怎么/适合）不得把无关查询变成"有证据"。

    用**真实语料标定**的阈值（score≥12 / matched≥3）跑一次，验证闸门确实会拦掉弱命中。
    """
    import dataclasses

    from app.services.retrieval_service import RetrievalService

    strict = RetrievalService(
        services.store,
        None,
        dataclasses.replace(
            services.settings, rag_min_relevance_score=12.0, rag_min_matched_terms=3
        ),
    )
    loose = RetrievalService(
        services.store,
        None,
        dataclasses.replace(
            services.settings, rag_min_relevance_score=0.0, rag_min_matched_terms=1
        ),
    )
    assert (await strict.search("今天天气怎么样适合去钓鱼吗")).is_empty
    # 正常查询不受闸门影响
    strict_hits = await strict.search("家庭血压应该怎么测量")
    assert strict_hits.hits
    assert strict_hits.hits[0].document_id == "HTN001"
    # 同一个查询在"关闭闸门"时命中集合不会更少
    loose_hits = await loose.search("家庭血压应该怎么测量")
    assert len(loose_hits.hits) >= len(strict_hits.hits)


async def test_relevance_gate_keeps_real_hits(services):
    result = await services.retrieval.search("家庭血压应该怎么测量")
    assert result.hits
    assert result.hits[0].document_id == "HTN001"


def test_build_context_numbering_matches_hits(services):
    from app.schemas.common import RetrievedChunk

    hits = [
        RetrievedChunk(
            chunk_id="C1",
            document_id="D1",
            title="标题一",
            section="第一节",
            authority_level="P0",
            source_url="https://example.invalid/1",
            content="内容一" * 10,
        ),
        RetrievedChunk(
            chunk_id="C2",
            document_id="D2",
            title="标题二",
            section="第二节",
            authority_level="P1",
            source_url="https://example.invalid/2",
            content="内容二" * 10,
        ),
    ]
    context, used = services.retrieval.build_context(hits)
    assert used > 0
    assert "[1]" in context and "[2]" in context
    assert "chunk_id=C1" in context
    assert context.index("[1]") < context.index("[2]")


def test_build_context_respects_max_chars(services):
    from app.schemas.common import RetrievedChunk

    hits = [
        RetrievedChunk(
            chunk_id=f"C{i}",
            document_id="D",
            title="T",
            source_url="https://example.invalid",
            content="很长的内容" * 200,
        )
        for i in range(10)
    ]
    context, used = services.retrieval.build_context(hits, max_chars=1200)
    assert used <= 1200 + 400
    assert context.count("[1]") == 1


@pytest.mark.parametrize("query", ["", "   ", "!!!"])
async def test_empty_query_returns_no_hits(services, query):
    result = await services.retrieval.search(query)
    assert result.is_empty


def test_retrieval_service_can_be_constructed(services):
    service = RetrievalService(services.store, None, services.settings)
    assert service.store is services.store
