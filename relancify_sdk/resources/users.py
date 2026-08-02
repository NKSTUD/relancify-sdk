from typing import Any, Dict

from relancify_sdk.http import AsyncHttpClient, HttpClient


class UsersResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def me(self) -> Dict[str, Any]:
        return self._client.request("GET", "/users/me")


class AsyncUsersResource:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def me(self) -> Dict[str, Any]:
        return await self._client.request("GET", "/users/me")
