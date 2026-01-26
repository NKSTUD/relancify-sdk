from typing import Any, Optional


class RelancifyError(Exception):
    pass


class ApiError(RelancifyError):
    def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
