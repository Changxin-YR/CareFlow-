"""RAG 问答（Retrieval-Augmented Generation）Schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.config import KB_IDS

from app.schemas.common import (
    Citation,
    LangCode,
    ModelMeta,
    PatientContext,
    RetrievedChunk,
    SafetyReport,
    StrictModel,
)


def validate_domains(value: list[str] | None) -> list[str] | None:
    """`domains` 必须是 KB 白名单内的取值。

    非法域若被静默丢弃，会把检索范围意外放大到全库 —— 这里选择快速失败。
    """
    if value is None:
        return None
    invalid = [item for item in value if item not in KB_IDS]
    if invalid:
        raise ValueError(f"未知知识域 {invalid}，可选值：{list(KB_IDS)}")
    return value


class RagOptions(StrictModel):
    top_k: int | None = Field(default=None, ge=1, le=20)
    domains: list[str] | None = Field(
        default=None,
        description="显式指定知识域（KB_CORE/KB_HTN/...）；为空则由 Domain Router 决定",
    )
    answer_language: LangCode = "zh"
    require_citations: bool = True
    max_context_chars: int | None = Field(default=None, ge=500, le=40000)
    include_retrieved: bool = True
    allow_no_evidence: bool = True
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)

    _check_domains = field_validator("domains")(validate_domains)


class RagRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000, description="患者/医生自然语言问题")
    patient_context: PatientContext | None = None
    options: RagOptions = Field(default_factory=RagOptions)

    @field_validator("query")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query 不能为空白")
        return value


class DroppedCitation(BaseModel):
    """被 Citation 校验器拒绝的非法引用（保留审计证据）。"""

    reason: str
    document_id: str = ""
    chunk_id: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class RagData(BaseModel):
    answer: str = ""
    insufficient_evidence: bool = True
    citations: list[Citation] = Field(default_factory=list)
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    context_chars: int = 0
    dropped_citations: list[DroppedCitation] = Field(default_factory=list)
    safety: SafetyReport = Field(default_factory=SafetyReport)
    model: ModelMeta = Field(default_factory=ModelMeta)


class RagResponse(BaseModel):
    data: RagData
