from typing import Any, Dict, List

from relancify_sdk.http import HttpClient
from relancify_sdk.resources._ids import normalize_uuid_path


class ApiKeysResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        return self._client.request("GET", "/api-keys/")

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.request("POST", "/api-keys/", json=payload)

    def revoke(self, api_key_id: str) -> None:
        normalized_id = normalize_uuid_path(api_key_id, field_name="api_key_id")
        self._client.request("DELETE", f"/api-keys/{normalized_id}")
