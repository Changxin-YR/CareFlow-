"""医生随访草稿（FollowUp Draft）Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import (
    Citation,
    LangCode,
    ModelMeta,
    PatientContext,
    RetrievedChunk,
    SafetyReport,
    StrictModel,
)
from app.schemas.extraction import Observation
from app.schemas.rag import validate_domains


class FollowUpOptions(StrictModel):
    top_k: int | None = Field(default=None, ge=1, le=20)
    domains: list[str] | None = None
    answer_language: LangCode = "zh"
    include_education: bool = True
    max_questions: int = Field(default=6, ge=1, le=15)
    include_retrieved: bool = False

    _check_domains = field_validator("domains")(validate_domains)


class FollowUpRequest(StrictModel):
    checkin_text: str = Field(min_length=1, max_length=4000, description="本次随访记录原文")
    patient_context: PatientContext | None = None
    recent_observations: list[Observation] = Field(default_factory=list, max_length=100)
    options: FollowUpOptions = Field(default_factory=FollowUpOptions)

    @field_validator("checkin_text")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("checkin_text 不能为空白")
        return value


class FollowUpData(BaseModel):
    summary: str = ""
    questions: list[str] = Field(default_factory=list)
    education: str = ""
    citations: list[Citation] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    requires_human_confirmation: bool = True
    safety: SafetyReport = Field(default_factory=SafetyReport)
    model: ModelMeta = Field(default_factory=ModelMeta)


class FollowUpResponse(BaseModel):
    data: FollowUpData
