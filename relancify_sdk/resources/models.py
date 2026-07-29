from typing import Any, Dict

from relancify_sdk.http import AsyncHttpClient, HttpClient


class ModelsResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        return self._client.request(
            "GET",
            f"/models?page={max(1, int(page))}&page_size={max(1, min(100, int(page_size)))}",
        )


class AsyncModelsResource:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        return await self._client.request(
            "GET",
            f"/models?page={max(1, int(page))}&page_size={max(1, min(100, int(page_size)))}",
        )
