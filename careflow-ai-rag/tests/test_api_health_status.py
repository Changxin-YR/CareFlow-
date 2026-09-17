"""健康检查与运行状态 API 测试。"""

from __future__ import annotations

import json


def test_health_shape(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    for key in ("contract_version", "status", "qianfan", "manifest", "knowledge"):
        assert key in payload, key
    assert payload["contract_version"] == "CF-CONTRACT-2.0"
    assert payload["status"] == "ok"
    assert payload["manifest"] == "ok"
    assert payload["knowledge"] == "ok"
    assert payload["qianfan"] == "ok"  # mock provider 自报 ok（detail 里说明是 mock）


def test_health_never_leaks_secrets(client, monkeypatch):
    monkeypatch.setenv("QIANFAN_API_KEY", "super-secret-key")
    response = client.get("/health")
    assert "super-secret-key" not in response.text


def test_health_degraded_when_knowledge_missing(empty_client):
    response = empty_client.get("/health")
    payload = response.json()
    assert payload["manifest"] == "missing"
    assert payload["knowledge"] == "missing"
    assert payload["status"] in {"degraded", "error"}


def test_health_sets_request_id_header(client):
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert response.headers.get("x-request-id") == "trace-123"


def test_health_generates_request_id_when_absent(client):
    response = client.get("/health")
    assert response.headers.get("x-request-id")


def test_status_envelope(client):
    response = client.get("/v1/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["operation"] == "status"
    assert payload["contract_version"] == "CF-CONTRACT-2.0"
    data = payload["data"]
    assert data["service"] == "careflow-ai-rag"
    assert data["ai_provider"] == "mock"
    names = {component["name"] for component in data["components"]}
    assert {"manifest", "knowledge", "qianfan", "safety"} <= names


def test_status_reports_manifest_statistics(client):
    response = client.get("/v1/status")
    data = response.json()["data"]
    assert data["manifest"]["documents_total"] == 5
    assert data["manifest"]["documents_active"] == 4
    assert data["knowledge"]["chunks_total"] == 4


def test_status_never_returns_api_key(client, monkeypatch):
    monkeypatch.setenv("QIANFAN_API_KEY", "leaky-key-value")
    monkeypatch.setenv("QIANFAN_APP_ID", "app-value")
    response = client.get("/v1/status")
    assert "leaky-key-value" not in response.text
    data = response.json()["data"]
    assert data["qianfan"]["api_key_set"] is False  # 该请求进程未重新加载 env


def test_status_lists_endpoints(client):
    data = client.get("/v1/status").json()["data"]
    assert "POST /v1/rag/answer" in data["endpoints"]
    assert "POST /v1/extract" in data["endpoints"]
    assert "POST /v1/followup/draft" in data["endpoints"]


def test_status_probe_flag_does_not_break_mock(client):
    response = client.get("/v1/status?probe=1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["qianfan"]["status"] in {"ok", "not_configured", "error"}


def test_openapi_schema_available(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/v1/extract" in schema["paths"]
    assert "/v1/rag/answer" in schema["paths"]
    assert "/v1/followup/draft" in schema["paths"]
    assert "/health" in schema["paths"]


def test_status_json_serializable(client):
    json.dumps(client.get("/v1/status").json(), ensure_ascii=False)
