from typing import Any, Dict, List

from relancify_sdk.http import HttpClient


class VoicesResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        return self._client.request("GET", "/voices")
