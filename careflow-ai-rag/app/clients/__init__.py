"""客户端工厂：根据 `AI_PROVIDER` 返回唯一的 LLM 客户端实例。"""

from __future__ import annotations

from app.clients.base import LLMClient, LLMResponse
from app.clients.mock import MockLLMClient
from app.clients.qianfan import QianfanClient
from app.core.config import Settings, load_settings

__all__ = ["LLMClient", "LLMResponse", "MockLLMClient", "QianfanClient", "get_llm_client", "reset_llm_client"]

_client: LLMClient | None = None


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """返回进程级单例客户端。"""
    global _client
    if _client is None:
        resolved = settings or load_settings()
        if resolved.ai_provider == "qianfan":
            _client = QianfanClient(resolved)
        else:
            _client = MockLLMClient()
    return _client


def set_llm_client(client: LLMClient | None) -> None:
    """测试用：注入自定义客户端。"""
    global _client
    _client = client


def reset_llm_client() -> None:
    global _client
    _client = None
