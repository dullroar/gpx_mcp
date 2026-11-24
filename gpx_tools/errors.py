"""Stable error codes. Clients can match on `code`."""

INVALID_INPUT = "invalid_input"
PATH_DENIED = "path_denied"
NOT_FOUND = "not_found"
LIMIT_EXCEEDED = "limit_exceeded"
CONFLICT = "conflict"
UNSUPPORTED = "unsupported"
NATIVE_FAILURE = "native_failure"

CODES = (
    INVALID_INPUT,
    PATH_DENIED,
    NOT_FOUND,
    LIMIT_EXCEEDED,
    CONFLICT,
    UNSUPPORTED,
    NATIVE_FAILURE,
)


class GpxToolError(Exception):
    """An expected failure with a stable code and a short message."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}
