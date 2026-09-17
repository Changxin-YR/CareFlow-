"""健康检查与运行状态 Schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """`GET /health` —— 契约规定的扁平结构。"""

    contract_version: str = "CF-CONTRACT-2.0"
    status: str = "ok"
    qianfan: str = "ok"
    manifest: str = "ok"
    knowledge: str = "ok"
    service: str = "careflow-ai-rag"
    version: str = "0.1.0"
    provider: str = "mock"
    time: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class ComponentStatus(BaseModel):
    name: str
    status: str = "ok"
    detail: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class StatusData(BaseModel):
    service: str = "careflow-ai-rag"
    version: str = "0.1.0"
    contract_version: str = "CF-CONTRACT-2.0"
    app_env: str = "development"
    ai_provider: str = "mock"
    started_at: str = ""
    uptime_seconds: float = 0.0
    components: list[ComponentStatus] = Field(default_factory=list)
    manifest: dict[str, Any] = Field(default_factory=dict)
    knowledge: dict[str, Any] = Field(default_factory=dict)
    qianfan: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    endpoints: list[str] = Field(default_factory=list)
