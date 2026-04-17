"""Shared MCP error types."""

from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_ERROR = "AUTH_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    TENANT_ERROR = "TENANT_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    ERPNEXT_ERROR = "ERPNEXT_ERROR"
    AI_SERVICE_ERROR = "AI_SERVICE_ERROR"
    ENTITLEMENT_ERROR = "ENTITLEMENT_ERROR"


ERROR_RECOVERY_MAP: dict[ErrorCode, bool] = {
    ErrorCode.VALIDATION_ERROR: True,
    ErrorCode.NOT_FOUND: True,
    ErrorCode.AUTH_ERROR: False,
    ErrorCode.PERMISSION_ERROR: False,
    ErrorCode.TENANT_ERROR: False,
    ErrorCode.RATE_LIMIT: True,
    ErrorCode.ERPNEXT_ERROR: True,
    ErrorCode.AI_SERVICE_ERROR: True,
    ErrorCode.ENTITLEMENT_ERROR: False,
}


class MCPError(Exception):
    """Exception converted into the standard MCP error response."""

    def __init__(self, code: ErrorCode, message: str, details: Optional[str] = None):
        self.code = code
        self.message = message
        self.details = details
        self.recoverable = ERROR_RECOVERY_MAP.get(code, False)
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable,
        }
