"""千帆客户端单元测试 —— 用 httpx.MockTransport 模拟真实 HTTP 行为。

**这些测试验证的是客户端的 HTTP 层（认证头、超时、重试、错误映射、Token 统计），
不是千帆线上服务的可用性。** 真机验证见 HANDOFF.md 的 BLOCKED 清单。
"""

from __future__ import annotations

import dataclasses
import json
import logging

import httpx
import pytest

from app.clients.qianfan import QianfanClient
from app.core.config import load_settings
from app.core.errors import (
    ErrorCode,
    QianfanRateLimitError,
    QianfanTimeoutError,
    QianfanUnavailableError,
)

BASE = "https://qianfan-test.invalid"


def _settings(**overrides):
    settings = load_settings()
    payload = {
        "ai_provider": "qianfan",
        "qianfan_api_key": "secret-test-key-123456",
        "qianfan_app_id": "app-test-id",
        "qianfan_base_url": BASE,
        "qianfan_model": "ernie-test",
        "max_retries": 1,
        "request_timeout_seconds": 5,
    }
    payload.update(overrides)
    return dataclasses.replace(settings, **payload)


def _client(handler, **overrides):
    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient(transport=transport, timeout=5)
    return QianfanClient(_settings(**overrides), http_client=async_client)


def _json_response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


# --------------------------------------------------------------------------- #
# 认证
# --------------------------------------------------------------------------- #
async def test_bearer_token_header_sent():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        captured["app_id"] = request.headers.get("x-app-id")
        captured["url"] = str(request.url)
        return _json_response({"choices": [{"message": {"content": "hi"}}]})

    client = _client(handler)
    await client.chat([{"role": "user", "content": "你好"}])
    assert captured["auth"] == "Bearer secret-test-key-123456"
    assert captured["app_id"] == "app-test-id"
    assert captured["url"].endswith("/v2/chat/completions")


async def test_missing_api_key_raises_unavailable():
    client = _client(lambda request: _json_response({}), qianfan_api_key="")
    with pytest.raises(QianfanUnavailableError) as exc:
        await client.chat([{"role": "user", "content": "你好"}])
    assert "QIANFAN_API_KEY" in exc.value.message


# --------------------------------------------------------------------------- #
# 成功路径
# --------------------------------------------------------------------------- #
async def test_chat_parses_content_model_and_usage():
    payload = {
        "model": "ernie-test-0908",
        "choices": [{"message": {"content": "你好，我是千帆"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
    }
    client = _client(lambda request: _json_response(payload))
    response = await client.chat([{"role": "user", "content": "你好"}])
    assert response.text == "你好，我是千帆"
    assert response.model == "ernie-test-0908"
    assert response.usage.total_tokens == 20
    assert response.usage.prompt_tokens == 12
    assert response.provider == "qianfan"
    assert response.finish_reason == "stop"


async def test_chat_handles_legacy_text_field():
    payload = {"choices": [{"text": "旧版返回"}]}
    client = _client(lambda request: _json_response(payload))
    response = await client.chat([{"role": "user", "content": "x"}])
    assert response.text == "旧版返回"


async def test_chat_sends_temperature_and_max_tokens():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return _json_response({"choices": [{"message": {"content": "ok"}}]})

    client = _client(handler)
    await client.chat(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        temperature=0.3,
        max_tokens=256,
        task="extract",
    )
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 256
    assert captured["stream"] is False
    assert len(captured["messages"]) == 2


# --------------------------------------------------------------------------- #
# 错误映射
# --------------------------------------------------------------------------- #
async def test_rate_limit_mapped_and_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, text="qps limit exceeded")

    client = _client(handler, max_retries=1)
    with pytest.raises(QianfanRateLimitError) as exc:
        await client.chat([{"role": "user", "content": "x"}])
    assert exc.value.code is ErrorCode.QIANFAN_RATE_LIMIT
    assert calls["n"] == 2  # 初次 + 1 次重试


async def test_server_error_retried_then_unavailable():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="service unavailable")

    client = _client(handler, max_retries=1)
    with pytest.raises(QianfanUnavailableError):
        await client.chat([{"role": "user", "content": "x"}])
    assert calls["n"] == 2


async def test_auth_error_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="invalid token")

    client = _client(handler, max_retries=2)
    with pytest.raises(QianfanUnavailableError) as exc:
        await client.chat([{"role": "user", "content": "x"}])
    assert calls["n"] == 1  # 鉴权失败不重试
    assert "鉴权失败" in exc.value.message


async def test_bad_request_mapped_to_unavailable_with_details():
    client = _client(lambda request: httpx.Response(400, text="bad param"))
    with pytest.raises(QianfanUnavailableError) as exc:
        await client.chat([{"role": "user", "content": "x"}])
    assert exc.value.details["http_status"] == 400


async def test_timeout_mapped_and_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("too slow", request=request)

    client = _client(handler, max_retries=1)
    with pytest.raises(QianfanTimeoutError) as exc:
        await client.chat([{"role": "user", "content": "x"}])
    assert exc.value.code is ErrorCode.QIANFAN_TIMEOUT
    assert calls["n"] == 2


async def test_connect_error_mapped_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns fail", request=request)

    client = _client(handler, max_retries=0)
    with pytest.raises(QianfanUnavailableError):
        await client.chat([{"role": "user", "content": "x"}])


async def test_non_json_response_raises_unavailable():
    client = _client(lambda request: httpx.Response(200, text="<html>不是 JSON</html>"))
    with pytest.raises(QianfanUnavailableError):
        await client.chat([{"role": "user", "content": "x"}])


def test_max_retries_is_capped_by_config():
    from app.core.config import reload_settings

    import os

    os.environ["MAX_RETRIES"] = "99"
    settings = reload_settings()
    assert settings.max_retries <= 2
    os.environ.pop("MAX_RETRIES", None)
    reload_settings()


# --------------------------------------------------------------------------- #
# 知识库检索
# --------------------------------------------------------------------------- #
async def test_retrieve_knowledge_parses_chunks():
    payload = {
        "data": {
            "chunks": [
                {
                    "chunkId": "QF-1",
                    "content": "家庭血压测量建议静坐五分钟。",
                    "documentId": "HTN001",
                    "documentName": "高血压指南",
                    "score": 0.87,
                    "metadata": {
                        "authority_level": "P0",
                        "source_url": "https://example.invalid/a",
                    },
                }
            ]
        }
    }
    client = _client(lambda request: _json_response(payload))
    hits = await client.retrieve_knowledge("血压", ["kb-1"], top_k=3)
    assert len(hits) == 1
    assert hits[0].chunk_id == "QF-1"
    assert hits[0].document_id == "HTN001"
    assert hits[0].retrieval_source == "qianfan_kb"
    assert hits[0].authority_level == "P0"


async def test_retrieve_knowledge_empty_kb_ids_short_circuits():
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return _json_response({})

    client = _client(handler)
    assert await client.retrieve_knowledge("血压", [], top_k=3) == []
    assert called["n"] == 0


async def test_retrieve_knowledge_tolerates_flat_list():
    payload = {"results": [{"id": "1", "text": "内容", "documentId": "D1"}]}
    client = _client(lambda request: _json_response(payload))
    hits = await client.retrieve_knowledge("x", ["kb"], top_k=3)
    assert hits and hits[0].content == "内容"


# --------------------------------------------------------------------------- #
# Embedding
# --------------------------------------------------------------------------- #
async def test_embed_returns_vectors():
    payload = {"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
    client = _client(lambda request: _json_response(payload))
    vectors = await client.embed(["甲", "乙"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_count_mismatch_raises():
    payload = {"data": [{"embedding": [0.1]}]}
    client = _client(lambda request: _json_response(payload))
    with pytest.raises(QianfanUnavailableError):
        await client.embed(["甲", "乙"])


async def test_embed_empty_input_short_circuits():
    client = _client(lambda request: _json_response({}))
    assert await client.embed([]) == []


# --------------------------------------------------------------------------- #
# 健康检查与日志
# --------------------------------------------------------------------------- #
async def test_health_reports_ok_with_credentials():
    client = _client(lambda request: _json_response({}))
    status, detail = await client.health()
    assert status == "ok"
    assert "ernie" in detail


async def test_health_reports_not_configured_without_credentials():
    client = _client(lambda request: _json_response({}), qianfan_api_key="")
    status, _ = await client.health()
    assert status == "not_configured"


async def test_probe_returns_error_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network", request=request)

    client = _client(handler, max_retries=0)
    status, detail = await client.probe()
    assert status == "error"
    assert detail


async def test_api_key_never_written_to_logs(caplog):
    client = _client(lambda request: _json_response({"choices": [{"message": {"content": "ok"}}]}))
    with caplog.at_level(logging.INFO, logger="careflow.clients.qianfan"):
        await client.chat([{"role": "user", "content": "你好"}])
    joined = "\n".join(record.getMessage() + str(getattr(record, "event_fields", "")) for record in caplog.records)
    assert "secret-test-key-123456" not in joined


async def test_aclose_does_not_close_injected_client():
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _json_response({})))
    client = QianfanClient(_settings(), http_client=async_client)
    await client.aclose()
    assert async_client.is_closed is False
    await async_client.aclose()
