"""日志与脱敏测试。"""

from __future__ import annotations

import json
import logging

from app.core.logging_config import JsonFormatter, mask_value, request_id_var, scrub


def test_scrub_masks_sensitive_keys():
    payload = {
        "api_key": "abcdef1234567890",
        "Authorization": "Bearer xyz",
        "nested": {"client_secret": "s3cr3t-value-here"},
        "safe": "keep me",
    }
    cleaned = scrub(payload)
    assert "abcdef1234567890" not in json.dumps(cleaned, ensure_ascii=False)
    assert "s3cr3t-value-here" not in json.dumps(cleaned, ensure_ascii=False)
    assert cleaned["safe"] == "keep me"


def test_scrub_masks_phone_and_id_card():
    cleaned = scrub({"note": "联系电话13800138000，身份证110101199001011234"})
    assert "13800138000" not in cleaned["note"]
    assert "110101199001011234" not in cleaned["note"]


def test_scrub_handles_lists_and_scalars():
    cleaned = scrub([{"token": "aaaaaaaaaa"}, 3, "plain"])
    assert cleaned[1] == 3
    assert cleaned[2] == "plain"
    assert "aaaaaaaaaa" not in json.dumps(cleaned)


def test_mask_value_short_string():
    assert mask_value("abc") == "***"


def test_json_formatter_includes_request_id_and_fields():
    record = logging.LogRecord(
        name="careflow.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.event_fields = {"operation": "extract", "latency_ms": 12, "api_key": "supersecret12345"}
    token = request_id_var.set("rid-123")
    try:
        rendered = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)
    payload = json.loads(rendered)
    assert payload["message"] == "hello"
    assert payload["request_id"] == "rid-123"
    assert payload["operation"] == "extract"
    assert payload["latency_ms"] == 12
    assert "supersecret12345" not in rendered


def test_json_formatter_without_request_id():
    record = logging.LogRecord(
        name="careflow.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="no rid", args=(), exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert "request_id" not in payload
