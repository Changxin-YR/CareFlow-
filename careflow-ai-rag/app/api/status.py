"""`GET /v1/status` —— 运行状态与依赖明细。"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from app.api.deps import get_request_id, get_services_from_request, success_envelope
from app.core.contract import CONTRACT_VERSION
from app.schemas.status import ComponentStatus, StatusData

router = APIRouter(prefix="/v1", tags=["status"])

ENDPOINTS = [
    "GET /health",
    "GET /v1/status",
    "POST /v1/extract",
    "POST /v1/rag/answer",
    "POST /v1/followup/draft",
]


@router.get("/status", summary="运行状态")
async def status(
    request: Request,
    probe: bool = Query(default=False, description="是否真实探测千帆（会消耗配额）"),
) -> dict:
    services = get_services_from_request(request)
    store_health = services.store.health()
    stats = store_health["stats"]

    try:
        qianfan_status, qianfan_detail = await services.client.health()
    except Exception as exc:  # noqa: BLE001
        qianfan_status, qianfan_detail = "error", f"{type(exc).__name__}: {exc}"

    if probe and hasattr(services.client, "probe"):
        qianfan_status, qianfan_detail = await services.client.probe()
    elif probe and services.settings.ai_provider != "qianfan":
        qianfan_detail = f"{qianfan_detail}（AI_PROVIDER={services.settings.ai_provider}，无需探测）"

    components = [
        ComponentStatus(
            name="manifest",
            status=store_health["manifest"],
            detail=store_health["manifest_error"] or f"{stats['documents_total']} 篇文档",
            extra={"active": stats["documents_active"]},
        ),
        ComponentStatus(
            name="knowledge",
            status=store_health["knowledge"],
            detail=store_health["chunks_error"] or f"{stats['chunks_total']} 个切片",
            extra={"indexed_documents": stats["chunks_indexed_documents"]},
        ),
        ComponentStatus(
            name="qianfan", status=qianfan_status, detail=qianfan_detail,
            extra={"model": services.settings.qianfan_model},
        ),
        ComponentStatus(
            name="llm_client",
            status="ok",
            detail=f"provider={services.client.provider_name}",
        ),
        ComponentStatus(
            name="safety",
            status="ok",
            detail="规则引擎已加载（输入硬拦截 + 输出裁剪 + 红旗提示）",
        ),
    ]

    data = StatusData(
        service="careflow-ai-rag",
        version="0.1.0",
        contract_version=CONTRACT_VERSION,
        app_env=services.settings.app_env,
        ai_provider=services.settings.ai_provider,
        started_at=datetime.fromtimestamp(services.started_at, tz=timezone.utc).isoformat(
            timespec="seconds"
        ),
        uptime_seconds=round(time.time() - services.started_at, 3),
        components=components,
        manifest={
            "path": stats["manifest_path"],
            "documents_total": stats["documents_total"],
            "documents_active": stats["documents_active"],
            "by_status": stats["documents_by_status"],
            "by_authority_level": stats["documents_by_authority_level"],
            "by_kb": stats["documents_by_kb"],
            "problems": store_health["problems"],
        },
        knowledge={
            "path": stats["chunks_path"],
            "chunks_total": stats["chunks_total"],
            "chunks_by_kb": stats["chunks_by_kb"],
            "indexed_documents": stats["chunks_indexed_documents"],
        },
        qianfan={
            "status": qianfan_status,
            "detail": qianfan_detail,
            "base_url": services.settings.qianfan_base_url,
            "model": services.settings.qianfan_model,
            "app_id_set": bool(services.settings.qianfan_app_id),
            "api_key_set": bool(services.settings.qianfan_api_key),
            "kb_ids": {
                name: ("SET" if value else "") for name, value in services.settings.qianfan_kb_ids.items()
            },
            "kb_configured": services.settings.qianfan_kb_configured,
        },
        config=services.settings.redacted(),
        endpoints=ENDPOINTS,
    )
    return success_envelope("status", data, get_request_id(request))
