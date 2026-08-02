from typing import Any, Dict, List

from relancify_sdk.http import AsyncHttpClient, HttpClient


class VoicesResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        return self._client.request("GET", "/voices/")


class AsyncVoicesResource:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self) -> List[Dict[str, Any]]:
        return await self._client.request("GET", "/voices/")
