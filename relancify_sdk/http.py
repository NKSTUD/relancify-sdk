import asyncio
import time
from typing import Any, AsyncIterator, Dict, Iterator, Optional

import httpx

from relancify_sdk.auth import AuthConfig
from relancify_sdk.errors import ApiError

# ponytail: uniform 429 retry for every method; per-method idempotency policy
# is the upgrade path if non-idempotent requests need different handling.
_MAX_429_RETRIES = 2


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
            transport=httpx.HTTPTransport(retries=3),
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
        for attempt in range(_MAX_429_RETRIES + 1):
            response = self._client.request(
                method, path, json=json, headers=merged_headers
            )
            if response.status_code != 429 or attempt == _MAX_429_RETRIES:
                break
            time.sleep(min(self._to_error(response).retry_after_sec or 1, 10))
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
    def _to_error(response: httpx.Response) -> ApiError:
        detail = None
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        return ApiError(
            message=detail.get("detail") if isinstance(detail, dict) else str(detail),
            status_code=response.status_code,
            detail=detail,
            headers=response.headers,
        )

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise HttpClient._to_error(response)

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
            transport=httpx.AsyncHTTPTransport(retries=3),
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
        for attempt in range(_MAX_429_RETRIES + 1):
            response = await self._client.request(
                method,
                path,
                json=json,
                headers=merged_headers,
            )
            if response.status_code != 429 or attempt == _MAX_429_RETRIES:
                break
            await asyncio.sleep(
                min(HttpClient._to_error(response).retry_after_sec or 1, 10)
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
