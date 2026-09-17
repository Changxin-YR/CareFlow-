"""百度千帆（Qianfan / 文心一言 / AppBuilder）客户端。

**这是访问千帆的唯一入口** —— 认证、超时、重试、日志、错误映射、Token 统计
全部收敛在这里。

支持两种认证模式（由 `QIANFAN_AUTH_MODE` 选择）：

* ``bearer``（默认）：千帆 v2 OpenAI 兼容接口，``Authorization: Bearer <QIANFAN_API_KEY>``
* ``oauth``：旧版 ``aip.baidubce.com`` 网关，用 ``QIANFAN_APP_ID``(AK) +
  ``QIANFAN_API_KEY``(SK) 换取 access_token 后调用

> 说明：v2 知识库相关路径以 `QIANFAN_KB_RETRIEVE_PATH` /
> `QIANFAN_APPBUILDER_RUN_PATH` 暴露为可配置项 —— 千帆开放平台各版本路径存在
> 差异，真机联调时需要按当期文档核对。本模块的 HTTP 层、重试与错误映射已经过
> 本地测试；**未经真实凭据验证的部分在 HANDOFF.md 中明确标记为 BLOCKED**。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from app.clients.base import ChatMessage, LLMResponse
from app.core.config import Settings, load_settings
from app.core.errors import (
    ErrorCode,
    QianfanRateLimitError,
    QianfanTimeoutError,
    QianfanUnavailableError,
)
from app.core.logging_config import get_logger, log_event
from app.schemas.common import RetrievedChunk, Usage

logger = get_logger("clients.qianfan")

#: 千帆 v2 默认路径（可通过环境变量覆盖）
DEFAULT_PATHS: dict[str, str] = {
    "chat": "/v2/chat/completions",
    "embedding": "/v2/embeddings",
    "kb_retrieve": "/v2/knowledgeBase/retrieve",
    "appbuilder_run": "/v2/app/conversation/runs",
}

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class QianfanClient:
    """千帆 HTTP 客户端（异步）。"""

    provider_name = "qianfan"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        paths: dict[str, str] | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.model_name = self.settings.qianfan_model
        self._owns_client = http_client is None
        self._client = http_client
        self._paths = {**DEFAULT_PATHS, **(paths or {})}
        self._access_token: str | None = None
        self._access_token_expiry: float = 0.0
        self._auth_mode = (getattr(self.settings, "qianfan_auth_mode", "") or "bearer").lower()
        if not self.settings.qianfan_configured:
            logger.warning(
                "千帆凭据未配置（QIANFAN_API_KEY / QIANFAN_APP_ID 为空）——"
                "真实调用会失败，请在 .env 中补全"
            )

    # ------------------------------------------------------------------ HTTP
    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.request_timeout_seconds),
                follow_redirects=True,
                headers={"User-Agent": "careflow-ai-rag/0.1 (+qianfan)"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    def _url(self, key: str) -> str:
        return f"{self.settings.qianfan_base_url}{self._paths[key]}"

    async def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._auth_mode == "oauth":
            token = await self._oauth_token()
            headers["Authorization"] = f"Bearer {token}"
        else:
            if not self.settings.qianfan_api_key:
                raise QianfanUnavailableError(
                    "QIANFAN_API_KEY 未配置，无法调用千帆",
                    details={"hint": "在 .env 中设置 QIANFAN_API_KEY，或使用 AI_PROVIDER=mock"},
                )
            headers["Authorization"] = f"Bearer {self.settings.qianfan_api_key}"
        if self.settings.qianfan_app_id:
            # AppBuilder 侧需要 appid 参与签名/路由
            headers["X-App-Id"] = self.settings.qianfan_app_id
        return headers

    async def _oauth_token(self) -> str:
        """旧网关：用 AK/SK 换 access_token（带本地缓存）。"""
        now = time.time()
        if self._access_token and now < self._access_token_expiry - 30:
            return self._access_token
        client = await self._http()
        params = {
            "grant_type": "client_credentials",
            "client_id": self.settings.qianfan_app_id,
            "client_secret": self.settings.qianfan_api_key,
        }
        try:
            response = await client.post(self.settings.qianfan_oauth_url, params=params)
        except httpx.TimeoutException as exc:
            raise QianfanTimeoutError(f"千帆 OAuth 超时：{exc}") from exc
        except httpx.HTTPError as exc:
            raise QianfanUnavailableError(f"千帆 OAuth 网络异常：{exc}") from exc
        if response.status_code >= 400:
            raise QianfanUnavailableError(
                f"千帆 OAuth 失败 HTTP {response.status_code}",
                details={"body": response.text[:300]},
            )
        payload = response.json()
        token = str(payload.get("access_token", ""))
        if not token:
            raise QianfanUnavailableError("千帆 OAuth 未返回 access_token", details={"body": payload})
        self._access_token = token
        self._access_token_expiry = now + float(payload.get("expires_in", 2592000))
        return token

    # ---------------------------------------------------------------- 错误映射
    @staticmethod
    def _map_status(status: int, body: str, url: str) -> Exception:
        snippet = body[:500]
        if status == 429:
            return QianfanRateLimitError(
                "千帆触发限流（QPS/配额）", details={"http_status": status, "url": url, "body": snippet}
            )
        if status in (401, 403):
            return QianfanUnavailableError(
                "千帆鉴权失败（401/403），请检查 API Key / App ID / 授权范围",
                details={"http_status": status, "url": url, "body": snippet},
            )
        if status >= 500:
            return QianfanUnavailableError(
                f"千帆服务端错误 HTTP {status}",
                details={"http_status": status, "url": url, "body": snippet},
            )
        return QianfanUnavailableError(
            f"千帆请求被拒绝 HTTP {status}",
            code=ErrorCode.QIANFAN_UNAVAILABLE,
            details={"http_status": status, "url": url, "body": snippet},
        )

    async def _post_with_retry(
        self,
        key: str,
        payload: dict[str, Any],
        *,
        operation: str,
    ) -> dict[str, Any]:
        """带有限重试的 POST。最多 `MAX_RETRIES` 次重试（默认 1，上限 2）。"""
        url = self._url(key)
        attempts_allowed = self.settings.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts_allowed + 1):
            started = time.perf_counter()
            try:
                client = await self._http()
                headers = await self._headers()
                response = await client.post(url, headers=headers, json=payload)
                latency_ms = int((time.perf_counter() - started) * 1000)
                if response.status_code >= 400:
                    error = self._map_status(response.status_code, response.text, url)
                    retryable = response.status_code in RETRYABLE_STATUS
                    log_event(
                        logger,
                        "qianfan request failed",
                        operation=operation,
                        provider="qianfan",
                        model=self.model_name,
                        latency_ms=latency_ms,
                        success=False,
                        error_code=getattr(error, "code", ErrorCode.INTERNAL_ERROR).value
                        if isinstance(getattr(error, "code", None), ErrorCode)
                        else str(getattr(error, "code", ErrorCode.INTERNAL_ERROR)),
                        http_status=response.status_code,
                        attempt=attempt,
                    )
                    if retryable and attempt < attempts_allowed:
                        last_error = error
                        await asyncio.sleep(min(2 ** (attempt - 1) * 0.5, 2.0))
                        continue
                    raise error

                log_event(
                    logger,
                    "qianfan request ok",
                    operation=operation,
                    provider="qianfan",
                    model=self.model_name,
                    latency_ms=latency_ms,
                    success=True,
                    attempt=attempt,
                )
                return response.json()

            except (QianfanRateLimitError, QianfanUnavailableError, QianfanTimeoutError):
                raise
            except httpx.TimeoutException as exc:
                last_error = QianfanTimeoutError(
                    f"千帆请求超时（>{self.settings.request_timeout_seconds}s）",
                    details={"operation": operation, "url": url},
                )
                log_event(
                    logger,
                    "qianfan timeout",
                    operation=operation,
                    provider="qianfan",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    success=False,
                    error_code=ErrorCode.QIANFAN_TIMEOUT.value,
                    attempt=attempt,
                )
                if attempt < attempts_allowed:
                    await asyncio.sleep(min(2 ** (attempt - 1) * 0.5, 2.0))
                    continue
                raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = QianfanUnavailableError(
                    f"千帆网络异常：{type(exc).__name__}",
                    details={"operation": operation, "url": url},
                )
                log_event(
                    logger,
                    "qianfan transport error",
                    operation=operation,
                    provider="qianfan",
                    success=False,
                    error_code=ErrorCode.QIANFAN_UNAVAILABLE.value,
                    attempt=attempt,
                    error=type(exc).__name__,
                )
                if attempt < attempts_allowed:
                    await asyncio.sleep(min(2 ** (attempt - 1) * 0.5, 2.0))
                    continue
                raise last_error from exc
            except json.JSONDecodeError as exc:
                raise QianfanUnavailableError(
                    "千帆返回非 JSON 响应", details={"operation": operation, "url": url}
                ) from exc

        raise last_error or QianfanUnavailableError("千帆调用失败", details={"operation": operation})

    # ------------------------------------------------------------------- Chat
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
        payload: dict[str, Any] = {
            "model": model or self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format

        started = time.perf_counter()
        body = await self._post_with_retry("chat", payload, operation=task or "chat")
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = ""
        finish_reason = ""
        choices = body.get("choices") or []
        if choices:
            first = choices[0] or {}
            message = first.get("message") or {}
            text = message.get("content") or first.get("text") or ""
            finish_reason = str(first.get("finish_reason", ""))

        raw_usage = body.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(raw_usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(raw_usage.get("completion_tokens", 0) or 0),
            total_tokens=int(raw_usage.get("total_tokens", 0) or 0),
        )
        return LLMResponse(
            text=text,
            model=str(body.get("model", payload["model"])),
            provider=self.provider_name,
            usage=usage,
            latency_ms=latency_ms,
            attempts=1,
            finish_reason=finish_reason,
            raw=body,
        )

    # --------------------------------------------------------------- Embedding
    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {"model": model or self.settings.qianfan_embedding_model, "input": texts}
        body = await self._post_with_retry("embedding", payload, operation="embedding")
        data = body.get("data") or []
        vectors = [item.get("embedding", []) for item in data if isinstance(item, dict)]
        if len(vectors) != len(texts):
            raise QianfanUnavailableError(
                "千帆 embedding 返回数量与请求不一致",
                details={"requested": len(texts), "returned": len(vectors)},
            )
        return vectors

    # ------------------------------------------------------- 千帆知识库检索（RAG）
    async def retrieve_knowledge(
        self,
        query: str,
        kb_ids: list[str],
        *,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """调用千帆知识库检索接口。

        真实响应结构在不同平台版本间存在差异，这里做**宽容解析**：
        兼容 ``data.chunks`` / ``data.records`` / ``results`` 等字段。
        """
        kb_ids = [kb for kb in kb_ids if kb]
        if not kb_ids:
            return []
        payload: dict[str, Any] = {
            "knowledgeBaseIds": kb_ids,
            "query": query,
            "topK": top_k,
        }
        body = await self._post_with_retry("kb_retrieve", payload, operation="kb_retrieve")
        candidates: Any = (
            body.get("data")
            or body.get("result")
            or body.get("results")
            or body.get("chunks")
            or []
        )
        if isinstance(candidates, dict):
            candidates = (
                candidates.get("chunks")
                or candidates.get("records")
                or candidates.get("results")
                or []
            )
        hits: list[RetrievedChunk] = []
        for index, item in enumerate(candidates if isinstance(candidates, list) else []):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("text") or item.get("chunk") or "")
            if not content:
                continue
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            hits.append(
                RetrievedChunk(
                    chunk_id=str(item.get("chunkId") or item.get("id") or f"QF-{index}"),
                    document_id=str(
                        item.get("documentId") or meta.get("document_id") or item.get("docId") or ""
                    ),
                    title=str(item.get("documentName") or meta.get("title") or ""),
                    section=str(item.get("title") or meta.get("section") or ""),
                    authority=str(meta.get("authority", "")),
                    authority_level=str(meta.get("authority_level", "")),
                    source_url=str(meta.get("source_url") or item.get("url") or ""),
                    score=float(item.get("score", 0.0) or 0.0),
                    retrieval_source="qianfan_kb",
                    content=content,
                )
            )
        return hits[:top_k]

    # ------------------------------------------------- AppBuilder 应用对话（带 KB）
    async def appbuilder_run(
        self,
        query: str,
        *,
        conversation_id: str = "",
        stream: bool = False,
    ) -> dict[str, Any]:
        """调用 AppBuilder 应用（应用侧已挂载知识库）——可选增强路径。"""
        payload: dict[str, Any] = {
            "app_id": self.settings.qianfan_app_id,
            "query": query,
            "stream": stream,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        return await self._post_with_retry("appbuilder_run", payload, operation="appbuilder_run")

    # ------------------------------------------------- 知识库「新增文档」（可配置路径）
    async def create_document(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """调用千帆知识库「新增文档」接口。

        路径由调用方传入（默认见 `scripts/sync_qianfan.py::CREATE_DOC_PATH`），
        因为该接口路径在不同平台版本间存在差异，硬编码会很容易失效。

        > 该方法**尚未用真实凭据验证**，见 HANDOFF.md 的 BLOCKED 清单 B3。
        """
        key = "__kb_create_document__"
        self._paths[key] = path
        try:
            return await self._post_with_retry(key, payload, operation="kb_create_document")
        finally:
            self._paths.pop(key, None)

    # ------------------------------------------------------------------ Health
    async def health(self) -> tuple[str, str]:
        """健康检查：只做**本地凭据存在性**判断 + 可选轻量探测，不消耗配额。"""
        if not self.settings.qianfan_configured:
            return "not_configured", "缺少 QIANFAN_API_KEY / QIANFAN_APP_ID"
        return "ok", f"凭据已配置（model={self.model_name}，{self._auth_mode} 模式）"

    async def probe(self) -> tuple[str, str]:
        """真实探测（消耗配额，仅由 /v1/status?probe=1 或脚本显式触发）。"""
        try:
            response = await self.chat(
                [{"role": "user", "content": "ping"}], task="health_probe", max_tokens=4
            )
        except Exception as exc:  # noqa: BLE001 - 健康检查不应抛出
            return "error", f"{type(exc).__name__}: {exc}"[:300]
        return "ok", f"model={response.model} latency_ms={response.latency_ms}"
