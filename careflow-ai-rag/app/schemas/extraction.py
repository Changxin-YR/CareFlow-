"""结构化提取（Extraction）Schema。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ModelMeta, PatientContext, SafetyReport, StrictModel, TolerantModel


class ObservationType(str, Enum):
    """允许被提取的观察类型白名单。

    不在白名单内的内容一律**不得**出现在输出中（防止模型自行发明字段）。
    """

    BLOOD_PRESSURE = "BLOOD_PRESSURE"
    BLOOD_GLUCOSE = "BLOOD_GLUCOSE"
    HBA1C = "HBA1C"
    BLOOD_LIPID = "BLOOD_LIPID"
    URIC_ACID = "URIC_ACID"
    WEIGHT = "WEIGHT"
    HEIGHT = "HEIGHT"
    BMI = "BMI"
    WAIST = "WAIST"
    HEART_RATE = "HEART_RATE"
    BLOOD_OXYGEN = "BLOOD_OXYGEN"
    BODY_TEMPERATURE = "BODY_TEMPERATURE"
    PEAK_FLOW = "PEAK_FLOW"
    SYMPTOM = "SYMPTOM"
    MEDICATION = "MEDICATION"
    ADHERENCE = "ADHERENCE"
    SMOKING = "SMOKING"
    ALCOHOL = "ALCOHOL"
    EXERCISE = "EXERCISE"
    DIET = "DIET"
    SLEEP = "SLEEP"
    MOOD = "MOOD"
    FOLLOWUP_EVENT = "FOLLOWUP_EVENT"
    OTHER = "OTHER"


class Observation(TolerantModel):
    """单条结构化观察。

    字段含义与契约示例保持一致：`value` 是结构化数值，`source_text` 必须
    是用户原文中的**连续片段**（用于患者确认与审计回溯）。
    """

    type: ObservationType
    value: dict[str, Any] = Field(default_factory=dict)
    unit: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_text: str = ""
    needs_confirmation: bool = False
    observed_at: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, raw: Any) -> dict[str, Any]:
        """容忍模型把 value 写成标量 / 字符串。"""
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        return {"value": raw}

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, raw: Any) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 0.5
        return min(1.0, max(0.0, value))

    @model_validator(mode="after")
    def _require_numeric_payload(self) -> "Observation":
        if not self.value and self.type is not ObservationType.OTHER:
            # 空 value 只允许出现在明确的"无数据"场景；此处不报错，交由服务层补充
            pass
        if self.type is ObservationType.BLOOD_PRESSURE:
            has_pair = "systolic" in self.value and "diastolic" in self.value
            has_scalar = "value" in self.value
            if not (has_pair or has_scalar):
                self.needs_confirmation = True
        return self


class ExtractionOptions(StrictModel):
    include_model_meta: bool = True
    include_retrieval_hints: bool = False
    max_observations: int = Field(default=40, ge=1, le=200)


class ExtractionRequest(StrictModel):
    text: str = Field(min_length=1, max_length=4000, description="患者自然语言健康记录原文")
    patient_context: PatientContext | None = None
    options: ExtractionOptions = Field(default_factory=ExtractionOptions)

    @field_validator("text")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text 不能为空白")
        return value


class ExtractionData(BaseModel):
    observations: list[Observation] = Field(default_factory=list)
    unmatched_text: str = ""
    observation_types: list[str] = Field(default_factory=list)
    needs_patient_confirmation: bool = True
    safety: SafetyReport = Field(default_factory=SafetyReport)
    model: ModelMeta = Field(default_factory=ModelMeta)


class ExtractionResponse(BaseModel):
    """仅用于文档与 OpenAPI 展示；实际由统一信封包裹。"""

    data: ExtractionData
