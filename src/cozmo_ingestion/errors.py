"""Stable error codes shared by adapters, validation and storage."""


class IngestionError(ValueError):
    """A validation failure with a stable, machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise IngestionError(code, message)
