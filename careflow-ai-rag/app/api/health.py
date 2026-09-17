"""`GET /health` —— 契约规定的扁平健康检查。"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

from app.api.deps import get_services_from_request
from app.core.contract import CONTRACT_VERSION
from app.schemas.status import HealthResponse

router = APIRouter(tags=["health"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health(request: Request, response: Response) -> HealthResponse:
    services = get_services_from_request(request)
    store_health = services.store.health()

    manifest_status = store_health["manifest"]
    knowledge_status = store_health["knowledge"]

    try:
        qianfan_status, qianfan_detail = await services.client.health()
    except Exception as exc:  # noqa: BLE001 - 健康检查不应 500
        qianfan_status, qianfan_detail = "error", f"{type(exc).__name__}: {exc}"

    degraded = manifest_status != "ok" or knowledge_status != "ok"
    if manifest_status in {"missing", "degraded"}:
        overall = "degraded"
    elif knowledge_status in {"missing", "empty"}:
        overall = "degraded"
    else:
        overall = "ok"
    if manifest_status == "missing":
        overall = "error"

    if overall == "error":
        response.status_code = 503

    return HealthResponse(
        contract_version=CONTRACT_VERSION,
        status=overall,
        qianfan=qianfan_status,
        manifest=manifest_status,
        knowledge=knowledge_status,
        service="careflow-ai-rag",
        version="0.1.0",
        provider=services.settings.ai_provider,
        time=_now(),
        detail={
            "qianfan_detail": qianfan_detail,
            "manifest_error": store_health["manifest_error"],
            "chunks_error": store_health["chunks_error"],
            "documents_total": store_health["stats"]["documents_total"],
            "documents_active": store_health["stats"]["documents_active"],
            "chunks_total": store_health["stats"]["chunks_total"],
            "uptime_seconds": round(time.time() - services.started_at, 3),
        },
    )
