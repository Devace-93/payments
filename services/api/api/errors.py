"""A single error type that every blueprint raises.

The app-level error handler (see ``api.app``) turns an :class:`ApiError` into the
JSON envelope the whole 3m4 family agrees on::

    {"error": {"code": "...", "message": "...", ...extra}}
"""
from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra or {}

    def to_dict(self) -> dict:
        error: dict = {"code": self.code, "message": self.message}
        error.update(self.extra)
        return {"error": error}
