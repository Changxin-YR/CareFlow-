"""CitationService 单元测试 —— 反幻觉引用的核心闸门。"""

from __future__ import annotations

from app.schemas.common import RetrievedChunk
from app.services.citation_service import CitationService


def _hit(**overrides) -> RetrievedChunk:
    payload = {
        "chunk_id": "HTN001-0001",
        "document_id": "HTN001",
        "title": "【测试夹具】高血压基层管理测试文档",
        "section": "一、家庭血压测量",
        "authority_level": "P0",
        "source_url": "https://example.invalid/fixture/htn001",
        "score": 0.5,
        "content": "家庭血压测量建议使用经过验证的上臂式电子血压计。",
    }
    payload.update(overrides)
    return RetrievedChunk(**payload)


def test_build_from_real_hit(services):
    service = CitationService(services.store)
    result = service.build([_hit()])
    assert len(result.citations) == 1
    citation = result.citations[0]
    assert citation.document_id == "HTN001"
    assert citation.chunk_id == "HTN001-0001"
    assert citation.source_url == "https://example.invalid/fixture/htn001"
    assert citation.authority_level == "P0"
    assert citation.quote.startswith("家庭血压测量")


def test_source_url_comes_from_manifest_not_from_chunk(services):
    """即使检索结果里的 URL 被篡改，输出也必须用 manifest 的权威 URL。"""
    service = CitationService(services.store)
    tampered = _hit(source_url="https://evil.invalid/fake")
    result = service.build([tampered])
    assert result.citations[0].source_url == "https://example.invalid/fixture/htn001"


def test_unknown_document_is_dropped(services):
    service = CitationService(services.store)
    result = service.build([_hit(document_id="NOT_IN_MANIFEST", chunk_id="X-1")])
    assert result.citations == []
    assert result.dropped[0].reason == "document_not_in_manifest"


def test_inactive_document_is_dropped(services):
    service = CitationService(services.store)
    result = service.build([_hit(document_id="COPD900", chunk_id="COPD900-0001")])
    assert result.citations == []
    assert result.dropped[0].reason == "document_not_active"
    assert result.dropped[0].detail["status"] == "superseded"


def test_missing_document_id_is_dropped(services):
    service = CitationService(services.store)
    result = service.build([_hit(document_id="", chunk_id="HTN001-0001")])
    assert result.citations == []
    assert result.dropped[0].reason == "missing_document_id"


def test_chunk_document_mismatch_is_dropped(services):
    service = CitationService(services.store)
    result = service.build([_hit(document_id="DM001", chunk_id="HTN001-0001")])
    assert result.citations == []
    assert result.dropped[0].reason == "chunk_document_mismatch"


def test_marker_out_of_range_recorded(services):
    service = CitationService(services.store)
    result = service.build([_hit()], used_markers=[5])
    # 越界标记被丢弃，但因为没有有效选择，会回退到 Top-N 真实命中
    assert any(item.reason == "marker_out_of_range" for item in result.dropped)
    assert len(result.citations) == 1


def test_marker_selects_only_marked_hits(services):
    service = CitationService(services.store)
    hits = [
        _hit(chunk_id="HTN001-0001", content="甲"),
        _hit(chunk_id="HTN001-0002", content="乙", section="二、生活方式干预"),
    ]
    result = service.build(hits, used_markers=[2])
    assert len(result.citations) == 1
    assert result.citations[0].chunk_id == "HTN001-0002"


def test_unknown_used_chunk_id_recorded(services):
    service = CitationService(services.store)
    result = service.build([_hit()], used_chunk_ids=["FAKE-9999"])
    assert any(item.reason == "chunk_not_retrieved_this_round" for item in result.dropped)


def test_deduplicate_by_chunk_id(services):
    service = CitationService(services.store)
    hit = _hit()
    result = service.build([hit, hit, hit])
    assert len(result.citations) == 1


def test_max_citations_cap(services):
    service = CitationService(services.store)
    hits = [_hit(chunk_id=f"HTN001-{i:04d}", content=f"内容{i}") for i in range(1, 8)]
    result = service.build(hits)
    assert len(result.citations) <= 3


def test_document_ids_deduped_and_sorted(services):
    service = CitationService(services.store)
    hits = [
        _hit(chunk_id="HTN001-0001"),
        _hit(chunk_id="DM001-0001", document_id="DM001", content="血糖监测"),
    ]
    result = service.build(hits)
    assert result.document_ids == sorted({c.document_id for c in result.citations})


def test_no_hits_produces_no_citations(services):
    service = CitationService(services.store)
    result = service.build([])
    assert result.citations == []
    assert result.dropped == []


def test_verify_citation_roundtrip(services):
    service = CitationService(services.store)
    citation = service.build([_hit()]).citations[0]
    ok, reason = service.verify_citation(citation)
    assert ok is True
    assert reason == ""


def test_verify_citation_rejects_unknown_document(services):
    service = CitationService(services.store)
    citation = service.build([_hit()]).citations[0]
    citation.document_id = "NOPE"
    ok, reason = service.verify_citation(citation)
    assert ok is False
    assert reason == "document_not_in_manifest"


def test_quote_is_truncated(services):
    service = CitationService(services.store)
    long_hit = _hit(content="很长的原文" * 200)
    result = service.build([long_hit])
    assert len(result.citations[0].quote) <= 160


def test_quote_never_empty_for_real_content(services):
    service = CitationService(services.store)
    result = service.build([_hit(content="短内容")])
    assert result.citations[0].quote == "短内容"
