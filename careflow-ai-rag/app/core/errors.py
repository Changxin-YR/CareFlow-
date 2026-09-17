"""CareFlow 康脉智护 —— 统一错误码与异常类型。

契约 CF-CONTRACT-2.0 规定：所有失败响应都携带 `error.code`，取值必须来自
`ErrorCode` 枚举。
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """契约错误码。"""

    INVALID_INPUT = "INVALID_INPUT"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    QIANFAN_TIMEOUT = "QIANFAN_TIMEOUT"
    QIANFAN_RATE_LIMIT = "QIANFAN_RATE_LIMIT"
    QIANFAN_UNAVAILABLE = "QIANFAN_UNAVAILABLE"
    RAG_NO_EVIDENCE = "RAG_NO_EVIDENCE"
    KNOWLEDGE_MANIFEST_INVALID = "KNOWLEDGE_MANIFEST_INVALID"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    CONTRACT_VERSION_ERROR = "CONTRACT_VERSION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: 错误码 → HTTP 状态码
ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.SCHEMA_VALIDATION_FAILED: 422,
    ErrorCode.QIANFAN_TIMEOUT: 504,
    ErrorCode.QIANFAN_RATE_LIMIT: 429,
    ErrorCode.QIANFAN_UNAVAILABLE: 503,
    ErrorCode.RAG_NO_EVIDENCE: 200,  # 无证据不是失败，是"有意义的空答案"
    ErrorCode.KNOWLEDGE_MANIFEST_INVALID: 500,
    ErrorCode.SAFETY_BLOCKED: 403,
    ErrorCode.CONTRACT_VERSION_ERROR: 400,
    ErrorCode.INTERNAL_ERROR: 500,
}


class CareFlowError(Exception):
    """所有业务异常的基类。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        else:
            self.http_status = ERROR_HTTP_STATUS.get(self.code, self.http_status)
        self.details: dict[str, Any] = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }


class InvalidInputError(CareFlowError):
    code = ErrorCode.INVALID_INPUT


class SchemaValidationError(CareFlowError):
    code = ErrorCode.SCHEMA_VALIDATION_FAILED


class QianfanTimeoutError(CareFlowError):
    code = ErrorCode.QIANFAN_TIMEOUT


class QianfanRateLimitError(CareFlowError):
    code = ErrorCode.QIANFAN_RATE_LIMIT


class QianfanUnavailableError(CareFlowError):
    code = ErrorCode.QIANFAN_UNAVAILABLE


class RagNoEvidenceError(CareFlowError):
    code = ErrorCode.RAG_NO_EVIDENCE


class ManifestInvalidError(CareFlowError):
    code = ErrorCode.KNOWLEDGE_MANIFEST_INVALID


class SafetyBlockedError(CareFlowError):
    code = ErrorCode.SAFETY_BLOCKED


class ContractVersionError(CareFlowError):
    code = ErrorCode.CONTRACT_VERSION_ERROR
