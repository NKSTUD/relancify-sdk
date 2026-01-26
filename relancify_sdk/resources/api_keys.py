from typing import Any, Dict, List

from relancify_sdk.http import HttpClient


class ApiKeysResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        return self._client.request("GET", "/api-keys")

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.request("POST", "/api-keys", json=payload)

    def revoke(self, api_key_id: str) -> None:
        self._client.request("DELETE", f"/api-keys/{api_key_id}")
