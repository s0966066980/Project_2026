"""Shared application errors (no framework types)."""


class ApplicationError(Exception):
    """Base application error with a safe machine code."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class NotFoundError(ApplicationError):
    def __init__(self, message: str = "not_found") -> None:
        super().__init__("not_found", message)


class ConflictError(ApplicationError):
    def __init__(self, message: str = "conflict") -> None:
        super().__init__("conflict", message)


class ValidationFailed(ApplicationError):
    def __init__(self, message: str = "validation_failed") -> None:
        super().__init__("validation_failed", message)
