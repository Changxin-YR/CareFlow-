"""FastAPI 依赖：服务容器、请求元数据、响应信封。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request

from app.clients import get_llm_client, reset_llm_client
from app.core.config import Settings, load_settings
from app.core.contract import CONTRACT_VERSION, envelope
from app.core.logging_config import request_id_var
from app.services.citation_service import CitationService
from app.services.extraction_service import ExtractionService
from app.services.followup_service import FollowUpService
from app.services.manifest_service import KnowledgeStore, get_knowledge_store, reset_knowledge_store
from app.services.rag_service import RagService
from app.services.retrieval_service import RetrievalService
from app.services.routing_service import RoutingService
from app.services.safety_service import SafetyService

SERVICE_VERSION = "0.1.0"


@dataclass
class Services:
    """所有服务的组装容器（进程级单例，测试可整体替换）。"""

    settings: Settings
    client: Any
    store: KnowledgeStore
    safety: SafetyService
    citation: CitationService
    retrieval: RetrievalService
    router: RoutingService
    extraction: ExtractionService
    rag: RagService
    followup: FollowUpService
    started_at: float = field(default_factory=time.time)


_services: Services | None = None


def build_services(settings: Settings | None = None) -> Services:
    resolved = settings or load_settings()
    client = get_llm_client(resolved)
    store = get_knowledge_store(resolved)
    store.load()
    safety = SafetyService()
    citation = CitationService(store)
    retrieval = RetrievalService(store, client, resolved)
    router = RoutingService(
        client, enable_llm=resolved.rag_enable_llm_router and resolved.is_qianfan
    )
    extraction = ExtractionService(client, settings=resolved, safety=safety)
    rag = RagService(
        store,
        client,
        settings=resolved,
        safety=safety,
        citation_service=citation,
        retrieval_service=retrieval,
        router=router,
    )
    followup = FollowUpService(
        store,
        client,
        settings=resolved,
        safety=safety,
        citation_service=citation,
        retrieval_service=retrieval,
        extraction_service=extraction,
        router=router,
    )
    return Services(
        settings=resolved,
        client=client,
        store=store,
        safety=safety,
        citation=citation,
        retrieval=retrieval,
        router=router,
        extraction=extraction,
        rag=rag,
        followup=followup,
    )


def get_services(*, force: bool = False) -> Services:
    global _services
    if _services is None or force:
        _services = build_services()
    return _services


def set_services(services: Services | None) -> None:
    global _services
    _services = services


def reset_services() -> None:
    """测试 / 配置热加载时重置所有单例。"""
    global _services
    _services = None
    reset_llm_client()
    reset_knowledge_store()


# --------------------------------------------------------------------------- #
# 请求上下文
# --------------------------------------------------------------------------- #
def get_request_id(request: Request | None = None) -> str:
    if request is not None:
        value = request.headers.get("X-Request-ID")
        if value:
            return value.strip()[:64]
    return request_id_var.get("")


def get_services_from_request(request: Request) -> Services:
    return getattr(request.app.state, "services", None) or get_services()


# --------------------------------------------------------------------------- #
# 响应信封
# --------------------------------------------------------------------------- #
def build_meta(data_object: Any) -> dict[str, Any]:
    """从数据对象上收集 meta（模型信息 + 服务层笔记）。"""
    model = getattr(data_object, "model", None)
    routing = getattr(data_object, "_routing", None) or {}
    citations = getattr(data_object, "citations", []) or []
    meta = {
        "contract_version": CONTRACT_VERSION,
        "service_version": SERVICE_VERSION,
        "provider": getattr(model, "provider", ""),
        "model": getattr(model, "model", ""),
        "latency_ms": int(getattr(model, "latency_ms", 0) or 0),
        "token_usage": getattr(model, "usage", None).model_dump()
        if getattr(model, "usage", None) is not None
        else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "prompt_version": getattr(model, "prompt_version", ""),
        "domains": list(getattr(data_object, "domains", []) or []),
        "document_ids": sorted({item.document_id for item in citations}),
        "degraded": bool(getattr(data_object, "_degraded", False)),
        "notes": [str(item) for item in (getattr(data_object, "_notes", None) or [])],
    }
    if routing:
        meta["routing"] = routing
    return meta


def success_envelope(operation: str, data_object: Any, request_id: str = "") -> dict[str, Any]:
    payload = data_object.model_dump(mode="json")
    return envelope(operation, payload, request_id=request_id, meta=build_meta(data_object))
