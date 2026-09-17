"""CareFlow 康脉智护 —— AI Gateway 服务入口。

契约：**CF-CONTRACT-2.0**
默认监听：``0.0.0.0:8100``
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.responses import JSONResponse as StarletteJSONResponse

from app.api import extraction as extraction_api
from app.api import followup as followup_api
from app.api import health as health_api
from app.api import rag as rag_api
from app.api import status as status_api
from app.api.deps import get_services, reset_services
from app.core.config import load_settings
from app.core.contract import (
    CONTRACT_VERSION,
    CONTRACT_VERSION_HEADER,
    check_contract_version,
    error_envelope,
)
from app.core.errors import CareFlowError, ContractVersionError, ErrorCode
from app.core.logging_config import configure_logging, get_logger, log_event, request_id_var

logger = get_logger("main")

SERVICE_NAME = "careflow-ai-rag"


# --------------------------------------------------------------------------- #
# 中间件（纯 ASGI，避免 BaseHTTPMiddleware 的 contextvar 传播问题）
# --------------------------------------------------------------------------- #
class RequestContextMiddleware:
    """注入 request_id、校验契约版本、记录访问日志。"""

    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = (headers.get("x-request-id") or uuid.uuid4().hex[:16]).strip()[:64]
        token = request_id_var.set(request_id)
        # 让 Request.state 也能读到（异常处理器与端点使用）
        scope.setdefault("state", {})["request_id"] = request_id
        path = scope.get("path", "")
        method = scope.get("method", "")

        # 契约版本校验（/health 除外：运维探针不应被契约阻塞）
        if path.startswith("/v1"):
            try:
                check_contract_version(headers.get(CONTRACT_VERSION_HEADER.lower()))
            except ContractVersionError as exc:
                response = StarletteJSONResponse(
                    status_code=exc.http_status,
                    content=error_envelope(
                        "unknown",
                        exc.code.value,
                        exc.message,
                        request_id=request_id,
                        details=exc.details,
                    ),
                    headers={
                        "X-Request-ID": request_id,
                        "X-CF-Contract-Version": CONTRACT_VERSION,
                    },
                )
                await response(scope, receive, send)
                request_id_var.reset(token)
                return

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):  # noqa: ANN001
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 0))
                raw_headers = list(message.get("headers") or [])
                # 异常处理器可能已经设置过这两个头；无条件追加会产生**重复响应头**，
                # 而客户端对重复头的处理不一致，会让追踪 ID / 契约版本变得不可靠。
                present = {key.lower() for key, _value in raw_headers}
                if b"x-request-id" not in present:
                    raw_headers.append((b"x-request-id", request_id.encode()))
                if b"x-cf-contract-version" not in present:
                    raw_headers.append((b"x-cf-contract-version", CONTRACT_VERSION.encode()))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            log_event(
                logger,
                "http request",
                operation=f"{method} {path}",
                success=200 <= status_code < 400,
                latency_ms=latency_ms,
                http_status=status_code,
            )
            request_id_var.reset(token)


# --------------------------------------------------------------------------- #
# 生命周期
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    configure_logging(settings.log_level, json_output=settings.app_env != "development")
    log_event(
        logger,
        "careflow-ai-rag starting",
        operation="startup",
        provider=settings.ai_provider,
        model=settings.qianfan_model,
        app_env=settings.app_env,
    )
    services = get_services(force=True)
    store_health = services.store.health()
    log_event(
        logger,
        "knowledge store loaded",
        operation="startup",
        success=store_health["manifest"] == "ok" and store_health["knowledge"] == "ok",
        documents=store_health["stats"]["documents_total"],
        chunks=store_health["stats"]["chunks_total"],
        problems=len(store_health["problems"]),
    )
    app.state.services = services
    try:
        yield
    finally:
        client = getattr(services, "client", None)
        if client is not None and hasattr(client, "aclose"):
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                logger.warning("client close failed", exc_info=True)
        reset_services()
        log_event(logger, "careflow-ai-rag stopped", operation="shutdown")


# --------------------------------------------------------------------------- #
# 应用
# --------------------------------------------------------------------------- #
def create_app() -> FastAPI:
    settings = load_settings()
    configure_logging(settings.log_level, json_output=settings.app_env != "development")

    application = FastAPI(
        title="CareFlow 康脉智护 AI Gateway",
        description=(
            "基层慢病多病共管与智能随访平台的 AI/RAG 子系统。\n\n"
            "契约版本：**CF-CONTRACT-2.0**。\n\n"
            "本服务只负责理解、提取、检索、解释、总结与草稿生成；"
            "权限、数据库、Rule Engine、Attention Level、正式保存与人工确认由 CareFlow 业务后端负责。"
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(RequestContextMiddleware)
    application.include_router(health_api.router)
    application.include_router(status_api.router)
    application.include_router(extraction_api.router)
    application.include_router(rag_api.router)
    application.include_router(followup_api.router)

    _register_exception_handlers(application)
    return application


def _request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "") or request_id_var.get("") or ""


def _register_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(CareFlowError)
    async def _careflow_error(request: Request, exc: CareFlowError) -> JSONResponse:
        request_id = _request_id_of(request)
        log_event(
            logger,
            "careflow error",
            operation=request.url.path,
            success=False,
            error_code=exc.code.value,
            error_message=exc.message,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=error_envelope(
                request.url.path.strip("/").replace("/", ".") or "unknown",
                exc.code.value,
                exc.message,
                request_id=request_id,
                details=exc.details,
            ),
            headers={"X-Request-ID": request_id, "X-CF-Contract-Version": CONTRACT_VERSION},
        )

    @application.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = _request_id_of(request)
        log_event(
            logger,
            "schema validation failed",
            operation=request.url.path,
            success=False,
            error_code=ErrorCode.SCHEMA_VALIDATION_FAILED.value,
        )
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                request.url.path.strip("/").replace("/", ".") or "unknown",
                ErrorCode.SCHEMA_VALIDATION_FAILED.value,
                "请求体不符合 CF-CONTRACT-2.0 Schema",
                request_id=request_id,
                details={"errors": _jsonable_errors(exc.errors())},
            ),
            headers={"X-Request-ID": request_id},
        )

    @application.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id_of(request)
        logger.exception("unhandled error")
        log_event(
            logger,
            "internal error",
            operation=request.url.path,
            success=False,
            error_code=ErrorCode.INTERNAL_ERROR.value,
        )
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                request.url.path.strip("/").replace("/", ".") or "unknown",
                ErrorCode.INTERNAL_ERROR.value,
                "服务内部错误，请稍后重试或联系运维并提供 request_id",
                request_id=request_id,
            ),
            headers={"X-Request-ID": request_id},
        )


def _jsonable_errors(errors: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for item in errors:
        cleaned.append(
            {
                "loc": [str(part) for part in item.get("loc", [])],
                "type": str(item.get("type", "")),
                "msg": str(item.get("msg", "")),
            }
        )
    return cleaned[:20]


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    _settings = load_settings()
    uvicorn.run(
        "app.main:app",
        host=_settings.host,
        port=_settings.port,
        log_level=_settings.log_level.lower(),
    )
