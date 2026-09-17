"""Mock LLM 客户端。

用途：
* ``AI_PROVIDER=mock`` 时让整条管线（Extraction / Router / RAG / FollowUp）
  在**无任何外部凭据**的环境下真实跑通并产生可断言的输出；
* 单元测试注入固定响应、异常、非法 JSON，用于验证降级与错误码。

**Mock 成功 ≠ 千帆真实验证通过。** 任何报告都必须区分二者。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

from app.clients.base import ChatMessage, LLMResponse
from app.core.logging_config import get_logger
from app.schemas.common import RetrievedChunk, Usage

logger = get_logger("clients.mock")

Handler = Callable[[str, list[ChatMessage]], str]


class MockLLMClient:
    """可编程假客户端。"""

    provider_name = "mock"

    def __init__(
        self,
        responses: list[str | Exception] | None = None,
        *,
        handler: Handler | None = None,
        model_name: str = "careflow-mock-1",
        latency_ms: int = 0,
        kb_hits: list[RetrievedChunk] | None = None,
    ) -> None:
        self.model_name = model_name
        self._responses = list(responses or [])
        self._handler = handler
        self._latency_ms = latency_ms
        self._kb_hits = list(kb_hits or [])
        self.calls: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ utils
    def _next_response(self, task: str, messages: list[ChatMessage]) -> str:
        if self._responses:
            item = self._responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if self._handler is not None:
            return self._handler(task, messages)
        return self._default_response(task, messages)

    @staticmethod
    def _default_response(task: str, messages: list[ChatMessage]) -> str:
        if task == "extract":
            return json.dumps({"observations": []}, ensure_ascii=False)
        if task == "route":
            return json.dumps({"domains": [], "reason": "mock"}, ensure_ascii=False)
        if task == "followup":
            return json.dumps(
                {"summary": "", "questions": [], "education": ""}, ensure_ascii=False
            )
        if task == "rag_answer":
            return json.dumps(
                {"answer": "", "insufficient_evidence": True, "used_chunk_ids": []},
                ensure_ascii=False,
            )
        return ""

    # ------------------------------------------------------------------- chat
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        task: str = "",
        temperature: float = 0.0,
        max_tokens: int | None = None,
        model: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        started = time.perf_counter()
        if self._latency_ms:
            await asyncio.sleep(self._latency_ms / 1000.0)
        self.calls.append(
            {
                "task": task,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": response_format,
            }
        )
        text = self._next_response(task, messages)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMResponse(
            text=text,
            model=model or self.model_name,
            provider=self.provider_name,
            usage=Usage(
                prompt_tokens=sum(len(m.get("content", "")) for m in messages) // 2,
                completion_tokens=len(text) // 2,
                total_tokens=(sum(len(m.get("content", "")) for m in messages) + len(text)) // 2,
            ),
            latency_ms=latency_ms,
            attempts=1,
            finish_reason="stop",
            raw={"mock": True},
        )

    # ---------------------------------------------------------------- 其他能力
    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """确定性伪向量：字符哈希分桶，保证同文本同向量、可复现。"""
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * 64
            for index, char in enumerate(text):
                vector[(ord(char) + index) % 64] += 1.0
            norm = sum(value * value for value in vector) ** 0.5 or 1.0
            vectors.append([round(value / norm, 6) for value in vector])
        return vectors

    async def retrieve_knowledge(
        self,
        query: str,
        kb_ids: list[str],
        *,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        return self._kb_hits[:top_k]

    async def health(self) -> tuple[str, str]:
        return "ok", "mock provider（不访问外部网络，不代表千帆可用）"

    async def aclose(self) -> None:
        return None
