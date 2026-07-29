from typing import Any, AsyncIterator, Dict, Iterator, Optional

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
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            follow_redirects=True,
        )
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
        response = self.request_response(
            method=method,
            path=path,
            json=json,
            headers=headers,
        )
        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def request_response(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        payload_headers = headers or {}
        merged_headers = self._auth.apply(payload_headers)
        response = self._client.request(method, path, json=json, headers=merged_headers)
        self._raise_for_error(response)
        return response

    def stream_lines(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Iterator[str]:
        payload_headers = headers or {}
        merged_headers = self._auth.apply(payload_headers)
        with self._client.stream(
            method,
            path,
            json=json,
            headers=merged_headers,
        ) as response:
            self._raise_for_error(response)
            yield from response.iter_lines()

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        if response.status_code >= 400:
            detail = None
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise ApiError(
                message=detail.get("detail")
                if isinstance(detail, dict)
                else str(detail),
                status_code=response.status_code,
                detail=detail,
                headers=response.headers,
            )

    def close(self) -> None:
        self._client.close()


class AsyncHttpClient:
    def __init__(
        self,
        base_url: str,
        auth: AuthConfig,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            follow_redirects=True,
        )
        self._auth = auth

    @property
    def base_url(self) -> str:
        return self._base_url

    async def request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        response = await self.request_response(
            method=method,
            path=path,
            json=json,
            headers=headers,
        )
        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    async def request_response(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        payload_headers = headers or {}
        merged_headers = self._auth.apply(payload_headers)
        response = await self._client.request(
            method,
            path,
            json=json,
            headers=merged_headers,
        )
        HttpClient._raise_for_error(response)
        return response

    async def stream_lines(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> AsyncIterator[str]:
        payload_headers = headers or {}
        merged_headers = self._auth.apply(payload_headers)
        async with self._client.stream(
            method,
            path,
            json=json,
            headers=merged_headers,
        ) as response:
            HttpClient._raise_for_error(response)
            async for line in response.aiter_lines():
                yield line

    async def close(self) -> None:
        await self._client.aclose()
