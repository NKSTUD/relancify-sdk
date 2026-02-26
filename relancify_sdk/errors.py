from typing import Any, Mapping, Optional


class RelancifyError(Exception):
    pass


class ApiError(RelancifyError):
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        detail: Any = None,
        headers: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        self.headers = {
            str(key).strip().lower(): str(value).strip()
            for key, value in (headers or {}).items()
            if str(key).strip()
        }

    @staticmethod
    def _to_optional_int(value: Any) -> Optional[int]:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            return None
        if parsed < 0:
            return None
        return parsed

    @property
    def payload(self) -> Any:
        if isinstance(self.detail, dict) and "detail" in self.detail:
            return self.detail.get("detail")
        return self.detail

    @property
    def code(self) -> Optional[str]:
        payload = self.payload
        if isinstance(payload, dict):
            raw = str(payload.get("code") or "").strip()
            return raw or None
        return None

    @property
    def scope(self) -> Optional[str]:
        payload = self.payload
        if isinstance(payload, dict):
            raw = str(payload.get("scope") or "").strip()
            return raw or None
        return None

    @property
    def limit(self) -> Optional[int]:
        payload = self.payload
        if isinstance(payload, dict):
            return self._to_optional_int(payload.get("limit"))
        return None

    @property
    def current(self) -> Optional[int]:
        payload = self.payload
        if isinstance(payload, dict):
            return self._to_optional_int(payload.get("current"))
        return None

    @property
    def retry_after_sec(self) -> Optional[int]:
        payload = self.payload
        if isinstance(payload, dict):
            parsed_payload = self._to_optional_int(payload.get("retry_after_sec"))
            if parsed_payload is not None and parsed_payload > 0:
                return parsed_payload

        parsed_header = self._to_optional_int(self.headers.get("retry-after"))
        if parsed_header is not None and parsed_header > 0:
            return parsed_header
        return None
