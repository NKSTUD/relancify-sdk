from typing import Any, Dict

from relancify_sdk.http import HttpClient


class OperationsResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def get(self, operation_id: str) -> Dict[str, Any]:
        return self._client.request("GET", f"/operations/{operation_id}")
