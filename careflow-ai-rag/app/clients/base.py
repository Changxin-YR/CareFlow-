"""LLM / 检索客户端的公共协议与数据结构。

CareFlow 运行时只允许通过 `app/clients/qianfan.py` 访问百度千帆。
本模块定义抽象接口，便于：
* `mock` 模式在无凭据环境下完整跑通管线；
* 单元测试注入可编程假客户端（超时、限流、非法 JSON）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.schemas.common import RetrievedChunk, Usage

ChatMessage = dict[str, str]


@dataclass
class LLMResponse:
    """一次模型调用的结果。"""

    text: str = ""
    model: str = ""
    provider: str = "mock"
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    attempts: int = 1
    finish_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMClient(Protocol):
    """所有模型客户端的统一接口。"""

    provider_name: str
    model_name: str

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        task: str = "",
        temperature: float = 0.0,
        max_tokens: int | None = None,
        model: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse: ...

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]: ...

    async def retrieve_knowledge(
        self,
        query: str,
        kb_ids: list[str],
        *,
        top_k: int = 5,
    ) -> list[RetrievedChunk]: ...

    async def health(self) -> tuple[str, str]: ...

    async def aclose(self) -> None: ...


def messages_to_preview(messages: list[ChatMessage], limit: int = 400) -> str:
    """把 messages 压成一行预览，仅用于日志（不记录完整患者文本）。"""
    if not messages:
        return ""
    last = messages[-1].get("content", "")
    text = str(last).replace("\n", " ")
    return text[:limit] + ("…" if len(text) > limit else "")
