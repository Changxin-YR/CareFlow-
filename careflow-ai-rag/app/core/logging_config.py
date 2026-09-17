"""CareFlow 康脉智护 —— 结构化日志。

要点：
* 单行 JSON，便于采集（Loki / ELK / 云日志）。
* 每条日志自动带上 `request_id`（读取 contextvar）。
* 敏感字段（api_key / secret / token / password / 手机号）一律脱敏。
* 明确禁止把密钥、Authorization 头写入日志。
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import time
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "auth",
    "secret",
    "secret_key",
    "password",
    "passwd",
    "client_secret",
    "qianfan_api_key",
    "token",
}

_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_ID_CARD_RE = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")


def mask_value(value: Any) -> Any:
    """对明显敏感的值做脱敏（保留长度信息以利排查）。"""
    if not isinstance(value, str):
        return value
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}(len={len(value)})"


def scrub(payload: Any, _depth: int = 0) -> Any:
    """递归脱敏字典 / 列表中的敏感字段。"""
    if _depth > 6:  # pragma: no cover - 防御环形结构
        return "..."
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for raw_key, value in payload.items():
            key = str(raw_key)
            if key.lower() in _SENSITIVE_KEYS:
                cleaned[key] = mask_value(value)
            else:
                cleaned[key] = scrub(value, _depth + 1)
        return cleaned
    if isinstance(payload, (list, tuple)):
        return [scrub(item, _depth + 1) for item in payload]
    if isinstance(payload, str):
        text = _PHONE_RE.sub(lambda m: m.group(1)[:3] + "****" + m.group(1)[-4:], payload)
        return _ID_CARD_RE.sub(lambda m: m.group(1)[:4] + "**********" + m.group(1)[-4:], text)
    return payload


class JsonFormatter(logging.Formatter):
    """把 LogRecord 渲染成单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_var.get("")
        if request_id:
            payload["request_id"] = request_id

        extra = getattr(record, "event_fields", None)
        if isinstance(extra, dict):
            payload.update(scrub(extra))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class HumanFormatter(logging.Formatter):
    """本地开发可读格式。"""

    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {record.name}: {record.getMessage()}"
        request_id = getattr(record, "request_id", None) or request_id_var.get("")
        if request_id:
            base = f"{base} [rid={request_id[:8]}]"
        extra = getattr(record, "event_fields", None)
        if isinstance(extra, dict) and extra:
            base = f"{base} {json.dumps(scrub(extra), ensure_ascii=False, default=str)}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


_configured = False


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    """配置根 logger（幂等）。"""
    global _configured
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if _configured:
        for handler in root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setFormatter(JsonFormatter() if json_output else HumanFormatter())
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else HumanFormatter())
    root.handlers = [handler]

    # 第三方库降噪
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"careflow.{name}")


def log_event(logger: logging.Logger, message: str, level: int = logging.INFO, **fields: Any) -> None:
    """结构化打点。字段名遵循契约：operation/provider/model/latency_ms/..."""
    logger.log(level, message, extra={"event_fields": scrub(fields)})
