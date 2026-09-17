"""CareFlow 康脉智护 —— 契约 CF-CONTRACT-2.0 定义与响应封装。

契约约定
--------
* `GET /health` 返回**扁平**结构（契约明文规定的五个键）。
* `GET /v1/status`、`POST /v1/extract`、`POST /v1/rag/answer`、
  `POST /v1/followup/draft` 返回**统一信封**：

  成功::

      {
        "contract_version": "CF-CONTRACT-2.0",
        "request_id": "...",
        "operation": "extract",
        "success": true,
        "data": { ... },
        "warnings": [],
        "meta": { ... }
      }

  失败::

      {
        "contract_version": "CF-CONTRACT-2.0",
        "request_id": "...",
        "operation": "extract",
        "success": false,
        "error": {"code": "INVALID_INPUT", "message": "...", "details": {}},
        "warnings": [],
        "meta": { ... }
      }

* 客户端可通过 `X-CF-Contract-Version` 请求头声明期望版本；
  与本服务版本不一致时返回 `CONTRACT_VERSION_ERROR`。
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ContractVersionError

CONTRACT_VERSION = "CF-CONTRACT-2.0"
SUPPORTED_CONTRACT_VERSIONS: frozenset[str] = frozenset({CONTRACT_VERSION})
CONTRACT_VERSION_HEADER = "X-CF-Contract-Version"

#: 契约中所有对外 operation 名
OPERATIONS: frozenset[str] = frozenset({"health", "status", "extract", "rag.answer", "followup.draft"})


def check_contract_version(header_value: str | None) -> str:
    """校验客户端声明的契约版本；缺省视为兼容。"""
    if header_value is None or not str(header_value).strip():
        return CONTRACT_VERSION
    requested = str(header_value).strip()
    if requested not in SUPPORTED_CONTRACT_VERSIONS:
        raise ContractVersionError(
            f"不支持的契约版本：{requested}",
            details={
                "requested": requested,
                "supported": sorted(SUPPORTED_CONTRACT_VERSIONS),
                "current": CONTRACT_VERSION,
            },
        )
    return requested


def envelope(
    operation: str,
    data: Any,
    *,
    request_id: str = "",
    warnings: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造成功信封。"""
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "operation": operation,
        "success": True,
        "data": data,
        "warnings": list(warnings or []),
        "meta": dict(meta or {}),
    }


def error_envelope(
    operation: str,
    code: str,
    message: str,
    *,
    request_id: str = "",
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造失败信封。"""
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "operation": operation,
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": dict(details or {}),
        },
        "warnings": list(warnings or []),
        "meta": dict(meta or {}),
    }
