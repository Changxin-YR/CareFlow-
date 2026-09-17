"""`POST /v1/followup/draft` —— 医生随访草稿（永远需要人工确认）。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import get_request_id, get_services_from_request, success_envelope
from app.schemas.followup import FollowUpRequest

router = APIRouter(prefix="/v1", tags=["followup"])


@router.post("/followup/draft", summary="随访草稿")
async def followup_draft(payload: FollowUpRequest, request: Request) -> dict:
    services = get_services_from_request(request)
    request_id = get_request_id(request)
    data = await services.followup.draft(payload, request_id=request_id)
    result = success_envelope("followup.draft", data, request_id)
    result["data"]["requires_human_confirmation"] = True
    return result
