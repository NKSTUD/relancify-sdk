from typing import Any, Dict, Optional

import httpx

from relancify_sdk.auth import AuthConfig
from relancify_sdk.errors import ApiError


class HttpClient:
    def __init__(
        self,
        base_url: str,
        auth: AuthConfig,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout)
        self._auth = auth

    @property
    def base_url(self) -> str:
        return self._base_url

    def request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        payload_headers = headers or {}
        merged_headers = self._auth.apply(payload_headers)
        response = self._client.request(method, path, json=json, headers=merged_headers)
        if response.status_code >= 400:
            detail = None
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise ApiError(
                message=detail.get("detail") if isinstance(detail, dict) else str(detail),
                status_code=response.status_code,
                detail=detail,
            )
        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def close(self) -> None:
        self._client.close()
