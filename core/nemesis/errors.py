"""NemesisError: a rejected Nemesis or wallet action, rendered as {"error": {code, message}}."""

from typing import Any

# HTTP status per error code (anything missing is 400).
STATUS = {
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "STEP_UP_REQUIRED": 403,
    "TWO_FACTOR_REQUIRED": 403,
    "NOT_FOUND": 404,
    "REQUEST_NOT_FOUND": 404,
    "FEATURE_DISABLED": 409,
    "NOT_ACTIVE": 409,
    "NOT_ELIGIBLE": 409,
    "ID_REQUIRED": 409,
    "ID_ALREADY_USED": 409,
    "EXCLUDED": 409,
    "ALREADY_ACTIVE": 409,
    "LIMIT_REACHED": 409,
    "DUPLICATE_REFERENCE": 409,
    "INSUFFICIENT_FUNDS": 409,
    "PAYOUT_NOT_SET": 409,
    "PAYOUT_PENDING": 409,
    "WITHDRAWAL_PENDING": 409,
    "DEPOSIT_OPEN": 409,
    "INVALID_STATE": 409,
    "HAS_FUNDS": 409,
    "RATE_LIMITED": 429,
    "LOCKED": 429,
}


class NemesisError(Exception):
    """`fields` names bad inputs; `extra` adds keys to the error object (e.g. eligibility)."""

    def __init__(
        self,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.fields, self.extra = code, message, fields, extra

    @property
    def status(self) -> int:
        return STATUS.get(self.code, 400)

    def payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.fields:
            error["fields"] = self.fields
        error.update(self.extra or {})
        return {"error": error}
