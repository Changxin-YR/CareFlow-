"""Schema 与契约层单元测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.contract import (
    CONTRACT_VERSION,
    SUPPORTED_CONTRACT_VERSIONS,
    check_contract_version,
    envelope,
    error_envelope,
)
from app.core.errors import ERROR_HTTP_STATUS, CareFlowError, ContractVersionError, ErrorCode
from app.core.json_utils import JSONParseError, extract_markers, loads_tolerant, normalize_whitespace
from app.schemas.common import Citation, PatientContext, RetrievedChunk
from app.schemas.extraction import ExtractionRequest, Observation, ObservationType
from app.schemas.followup import FollowUpRequest
from app.schemas.rag import RagOptions, RagRequest


# --------------------------------------------------------------------------- #
# 契约
# --------------------------------------------------------------------------- #
def test_contract_version_constant():
    assert CONTRACT_VERSION == "CF-CONTRACT-2.0"
    assert CONTRACT_VERSION in SUPPORTED_CONTRACT_VERSIONS


def test_check_contract_version_default_and_supported():
    assert check_contract_version(None) == CONTRACT_VERSION
    assert check_contract_version("") == CONTRACT_VERSION
    assert check_contract_version(CONTRACT_VERSION) == CONTRACT_VERSION


def test_check_contract_version_rejects_unknown():
    with pytest.raises(ContractVersionError) as exc:
        check_contract_version("CF-CONTRACT-1.0")
    assert exc.value.code is ErrorCode.CONTRACT_VERSION_ERROR
    assert exc.value.details["requested"] == "CF-CONTRACT-1.0"


def test_envelope_shapes():
    ok = envelope("extract", {"observations": []}, request_id="abc")
    assert ok["success"] is True
    assert ok["contract_version"] == CONTRACT_VERSION
    assert ok["request_id"] == "abc"
    assert ok["warnings"] == []
    bad = error_envelope("extract", ErrorCode.INVALID_INPUT.value, "坏的输入", request_id="abc")
    assert bad["success"] is False
    assert bad["error"]["code"] == "INVALID_INPUT"


def test_all_error_codes_have_http_status():
    for code in ErrorCode:
        assert code in ERROR_HTTP_STATUS, code


def test_required_error_codes_exist():
    required = {
        "INVALID_INPUT",
        "SCHEMA_VALIDATION_FAILED",
        "QIANFAN_TIMEOUT",
        "QIANFAN_RATE_LIMIT",
        "QIANFAN_UNAVAILABLE",
        "RAG_NO_EVIDENCE",
        "KNOWLEDGE_MANIFEST_INVALID",
        "SAFETY_BLOCKED",
        "CONTRACT_VERSION_ERROR",
        "INTERNAL_ERROR",
    }
    assert required <= {code.value for code in ErrorCode}


def test_careflow_error_payload():
    error = CareFlowError("boom", details={"k": 1})
    assert error.to_payload()["details"] == {"k": 1}


# --------------------------------------------------------------------------- #
# JSON 工具
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '好的，结果如下：{"a": 1}',
        '```\n{"a": 1}\n```',
    ],
)
def test_loads_tolerant(raw):
    assert loads_tolerant(raw) == {"a": 1}


def test_loads_tolerant_raises():
    with pytest.raises(JSONParseError):
        loads_tolerant("完全不是 JSON")


def test_extract_markers():
    assert extract_markers("见 [1] 与 [3]，还有重复 [1]") == [1, 3]
    assert extract_markers("没有引用") == []


def test_normalize_whitespace():
    assert normalize_whitespace("血压 158／96") == "血压158/96"


# --------------------------------------------------------------------------- #
# 通用 Schema
# --------------------------------------------------------------------------- #
def test_patient_context_forbids_unknown_field():
    with pytest.raises(ValidationError):
        PatientContext(name="张三")


def test_patient_context_allows_minimal_fields():
    context = PatientContext(patient_ref="p-1", age_years=64, sex="male", known_conditions=["HYPERTENSION"])
    assert context.age_years == 64


def test_citation_requires_source_url():
    citation = Citation(
        document_id="HTN001",
        chunk_id="HTN001-0001",
        title="t",
        source_url="https://example.invalid/x",
    )
    assert citation.authority_level == ""


def test_retrieved_chunk_defaults():
    hit = RetrievedChunk(chunk_id="c", document_id="d")
    assert hit.retrieval_source == "local_bm25"


# --------------------------------------------------------------------------- #
# Extraction Schema
# --------------------------------------------------------------------------- #
def test_extraction_request_rejects_blank_text():
    with pytest.raises(ValidationError):
        ExtractionRequest(text="   ")


def test_extraction_request_rejects_extra_field():
    with pytest.raises(ValidationError):
        ExtractionRequest(text="血压130/80", unexpected=1)


def test_observation_value_coercion():
    observation = Observation(type="WEIGHT", value=70.5, source_text="体重70.5")
    assert observation.value == {"value": 70.5}


def test_observation_confidence_clamped():
    observation = Observation(type="WEIGHT", value={"value": 70}, confidence=5, source_text="x")
    assert observation.confidence == 1.0


def test_observation_ignores_unknown_fields():
    observation = Observation(
        type="WEIGHT", value={"value": 70}, source_text="x", llm_comment="extra"
    )
    assert "llm_comment" not in observation.model_dump()


def test_observation_invalid_type_rejected():
    with pytest.raises(ValidationError):
        Observation(type="MADE_UP_TYPE", value={})


def test_blood_pressure_requires_pair_or_needs_confirmation():
    observation = Observation(type="BLOOD_PRESSURE", value={"systolic": 150})
    assert observation.needs_confirmation is True
    ok = Observation(type="BLOOD_PRESSURE", value={"systolic": 150, "diastolic": 95})
    assert ok.needs_confirmation is False


def test_observation_type_whitelist_size():
    assert len(list(ObservationType)) >= 20


# --------------------------------------------------------------------------- #
# RAG / FollowUp Schema
# --------------------------------------------------------------------------- #
def test_rag_request_defaults():
    request = RagRequest(query="高血压吃什么盐？")
    assert request.options.top_k is None
    assert request.options.allow_no_evidence is True


def test_rag_options_top_k_bounds():
    with pytest.raises(ValidationError):
        RagOptions(top_k=0)
    with pytest.raises(ValidationError):
        RagOptions(top_k=999)


def test_followup_request_defaults():
    request = FollowUpRequest(checkin_text="血压 150/95")
    assert request.options.max_questions == 6
    assert request.recent_observations == []


def test_followup_request_blank_rejected():
    with pytest.raises(ValidationError):
        FollowUpRequest(checkin_text="   ")
