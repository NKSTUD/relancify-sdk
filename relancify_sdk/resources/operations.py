from typing import Any, Dict

from relancify_sdk.http import HttpClient
from relancify_sdk.resources._ids import normalize_uuid_path


class OperationsResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def get(self, operation_id: str) -> Dict[str, Any]:
        normalized_id = normalize_uuid_path(operation_id, field_name="operation_id")
        return self._client.request("GET", f"/operations/{normalized_id}")
