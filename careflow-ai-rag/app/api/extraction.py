"""`POST /v1/extract` —— 患者自然语言健康记录 → 结构化 Observation。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import get_request_id, get_services_from_request, success_envelope
from app.core.logging_config import log_event, get_logger
from app.schemas.extraction import ExtractionRequest

router = APIRouter(prefix="/v1", tags=["extraction"])
logger = get_logger("api.extraction")


@router.post("/extract", summary="结构化提取")
async def extract(payload: ExtractionRequest, request: Request) -> dict:
    services = get_services_from_request(request)
    request_id = get_request_id(request)

    data = await services.extraction.extract(
        payload.text,
        patient_context=payload.patient_context,
        options=payload.options,
        request_id=request_id,
    )
    dropped = getattr(data, "_dropped", []) or []
    if dropped:
        log_event(
            logger,
            "extraction dropped observations",
            operation="extract",
            success=True,
            dropped=len(dropped),
        )
    result = success_envelope("extract", data, request_id)
    result["meta"]["dropped_observations"] = dropped[:20]
    result["meta"]["observation_count"] = len(data.observations)
    return result
