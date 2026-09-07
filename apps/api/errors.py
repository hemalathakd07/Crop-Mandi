from __future__ import annotations

from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, error: str, message: str, extra: dict | None = None):
        self.status_code = status_code
        self.error = error
        self.message = message
        self.extra = extra or {}
        super().__init__(message)

    def to_response(self) -> JSONResponse:
        body = {"error": self.error, "message": self.message, **self.extra}
        return JSONResponse(status_code=self.status_code, content=body)
