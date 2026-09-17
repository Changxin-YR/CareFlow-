"""CF-CONTRACT-2.0 契约一致性测试。"""

from __future__ import annotations

import pytest

from app.core.contract import CONTRACT_VERSION

V1_ENDPOINTS = [
    ("GET", "/v1/status", None),
    ("POST", "/v1/extract", {"text": "血压130/85"}),
    ("POST", "/v1/rag/answer", {"query": "家庭血压应该怎么测量？"}),
    ("POST", "/v1/followup/draft", {"checkin_text": "血压130/85"}),
]


def _call(client, method: str, url: str, payload):
    if method == "GET":
        return client.get(url)
    return client.post(url, json=payload)


@pytest.mark.parametrize(("method", "url", "payload"), V1_ENDPOINTS)
def test_envelope_has_contract_fields(client, method, url, payload):
    body = _call(client, method, url, payload).json()
    for key in ("contract_version", "request_id", "operation", "success", "meta", "warnings"):
        assert key in body, key
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["success"] is True


@pytest.mark.parametrize(("method", "url", "payload"), V1_ENDPOINTS)
def test_meta_contains_observability_fields(client, method, url, payload):
    meta = _call(client, method, url, payload).json()["meta"]
    for key in ("provider", "model", "latency_ms", "token_usage", "domains", "document_ids", "degraded"):
        assert key in meta, key


@pytest.mark.parametrize(("method", "url", "payload"), V1_ENDPOINTS)
def test_contract_version_header_accepted(client, method, url, payload):
    if method == "GET":
        response = client.get(url, headers={"X-CF-Contract-Version": CONTRACT_VERSION})
    else:
        response = client.post(url, json=payload, headers={"X-CF-Contract-Version": CONTRACT_VERSION})
    assert response.status_code == 200


@pytest.mark.parametrize(("method", "url", "payload"), V1_ENDPOINTS)
def test_contract_version_mismatch_rejected(client, method, url, payload):
    if method == "GET":
        response = client.get(url, headers={"X-CF-Contract-Version": "CF-CONTRACT-1.0"})
    else:
        response = client.post(
            url, json=payload, headers={"X-CF-Contract-Version": "CF-CONTRACT-1.0"}
        )
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "CONTRACT_VERSION_ERROR"
    assert body["error"]["details"]["requested"] == "CF-CONTRACT-1.0"


def test_health_ignores_contract_header(client):
    """健康探针不应被契约版本阻塞。"""
    response = client.get("/health", headers={"X-CF-Contract-Version": "CF-CONTRACT-0.1"})
    assert response.status_code == 200


def test_error_envelope_shape(client):
    body = client.post("/v1/extract", json={}).json()
    assert body["success"] is False
    assert set(body["error"].keys()) == {"code", "message", "details"}
    assert isinstance(body["warnings"], list)
    assert isinstance(body["meta"], dict)


def test_request_id_echoed_across_endpoints(client):
    headers = {"X-Request-ID": "trace-abc-123"}
    assert client.get("/v1/status", headers=headers).json()["request_id"] == "trace-abc-123"
    assert (
        client.post("/v1/extract", json={"text": "血压130/85"}, headers=headers).json()["request_id"]
        == "trace-abc-123"
    )
    assert (
        client.post("/v1/rag/answer", json={"query": "测量血压"}, headers=headers).json()["request_id"]
        == "trace-abc-123"
    )


def test_unknown_route_returns_404(client):
    assert client.get("/v1/does-not-exist").status_code == 404


def test_wrong_method_returns_405(client):
    assert client.get("/v1/extract").status_code == 405


def test_content_type_json_required(client):
    response = client.post(
        "/v1/extract", content="text=血压130/85", headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 422


def test_response_carries_contract_header(client):
    response = client.get("/v1/status")
    assert response.headers.get("x-cf-contract-version") == CONTRACT_VERSION


def test_all_endpoints_declared_in_status(client):
    endpoints = client.get("/v1/status").json()["data"]["endpoints"]
    assert len(endpoints) == 5
