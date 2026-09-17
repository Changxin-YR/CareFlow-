"""通用 Schema：契约元数据、患者上下文、检索命中、Citation。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import AUTHORITY_LEVELS

LangCode = Literal["zh", "en"]


class StrictModel(BaseModel):
    """请求侧模型：禁止多余字段，避免调用方误传而被静默忽略。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TolerantModel(BaseModel):
    """模型输出侧：容忍多余字段（LLM 常加解释性键），由服务层清洗。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class PatientContext(StrictModel):
    """最小必要的患者上下文。

    安全约束：**不接受姓名 / 身份证 / 手机号 / 住址**等直接标识符。
    真实的身份绑定由 CareFlow 业务后端通过 `patient_ref` 完成。
    """

    patient_ref: str | None = Field(default=None, max_length=64, description="业务后端的不可逆引用 ID")
    age_years: int | None = Field(default=None, ge=0, le=130)
    sex: Literal["male", "female", "other", "unknown"] | None = None
    known_conditions: list[str] = Field(default_factory=list, max_length=20)
    locale: LangCode = "zh"


class Usage(BaseModel):
    """Token 统计。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class RetrievedChunk(BaseModel):
    """本轮检索真实命中的知识片段（Citation 的唯一合法来源）。"""

    chunk_id: str
    document_id: str
    title: str = ""
    section: str = ""
    section_path: list[str] = Field(default_factory=list)
    authority: str = ""
    authority_level: str = ""
    version: str = ""
    effective_date: str = ""
    source_url: str = ""
    score: float = 0.0
    retrieval_source: str = "local_bm25"
    content: str = ""


class Citation(BaseModel):
    """由 CitationService **程序化构造**，绝不接受 LLM 自由生成。"""

    document_id: str
    chunk_id: str
    title: str
    section: str = ""
    authority: str = ""
    authority_level: str = ""
    version: str = ""
    effective_date: str = ""
    source_url: str
    quote: str = Field(default="", description="检索命中片段的原文截取，非模型生成")


class SafetyReport(BaseModel):
    """安全校验结论。只暴露信号，不给出临床决策。"""

    blocked: bool = False
    block_reason: str = ""
    flags: list[str] = Field(default_factory=list)
    redactions: list[str] = Field(default_factory=list)
    injection_detected: bool = False
    advice_seeking: bool = False
    requires_human_confirmation: bool = True


class ModelMeta(BaseModel):
    provider: str = "mock"
    model: str = ""
    latency_ms: int = 0
    attempts: int = 1
    prompt_version: str = ""
    usage: Usage = Field(default_factory=Usage)


class ContractMeta(BaseModel):
    """响应信封 `meta` 的固定部分。"""

    contract_version: str = "CF-CONTRACT-2.0"
    provider: str = "mock"
    model: str = ""
    latency_ms: int = 0
    token_usage: Usage = Field(default_factory=Usage)
    domains: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    degraded: bool = False
    notes: list[str] = Field(default_factory=list)


def _validate_authority_level(value: str) -> str:
    if value and value not in AUTHORITY_LEVELS:
        raise ValueError(f"authority_level 必须是 {AUTHORITY_LEVELS} 之一，收到 {value!r}")
    return value


class AuthorityMixin(BaseModel):
    authority_level: str = ""

    _check_authority = field_validator("authority_level")(_validate_authority_level)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
