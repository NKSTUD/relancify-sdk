from typing import Any, Dict

from relancify_sdk.http import HttpClient


class UsersResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def me(self) -> Dict[str, Any]:
        return self._client.request("GET", "/users/me")
