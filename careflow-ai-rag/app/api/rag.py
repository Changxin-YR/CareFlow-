"""`POST /v1/rag/answer` —— 基于官方知识库的 RAG 问答（带真实 Citation）。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import get_request_id, get_services_from_request, success_envelope
from app.schemas.rag import RagRequest

router = APIRouter(prefix="/v1", tags=["rag"])


@router.post("/rag/answer", summary="RAG 问答")
async def rag_answer(payload: RagRequest, request: Request) -> dict:
    services = get_services_from_request(request)
    request_id = get_request_id(request)
    data = await services.rag.answer(payload, request_id=request_id)
    return success_envelope("rag.answer", data, request_id)
