import re
from typing import Any, Dict, List, Optional

from relancify_sdk.http import HttpClient


TOOL_PUBLIC_ID_RE = re.compile(
    r"^tool_[0-9a-f]{8}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{12}$"
)
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def normalize_tool_id(value: str) -> str:
    raw = str(value or "").strip()
    if not TOOL_PUBLIC_ID_RE.fullmatch(raw):
        raise ValueError("Invalid tool_id. Expected format tool_<uuid>.")
    return raw


class ToolsResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        return self._client.request("GET", "/tools/")

    def get(self, tool_id: str) -> Dict[str, Any]:
        return self._client.request(
            "GET",
            f"/tools/{normalize_tool_id(tool_id)}",
        )

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.request("POST", "/tools/", json=payload)

    def create_http(
        self,
        *,
        name: str,
        url: str,
        input_schema: Dict[str, Any],
        description: Optional[str] = None,
        slug: Optional[str] = None,
        method: str = "GET",
        timeout_ms: int = 10_000,
        headers: Optional[Dict[str, str]] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        """Create an HTTP tool that Relancify can execute for hosted agents."""
        normalized_method = str(method or "").strip().upper()
        if normalized_method not in HTTP_METHODS:
            raise ValueError(
                "Invalid method. Expected GET, POST, PUT, PATCH, or DELETE."
            )

        payload: Dict[str, Any] = {
            "name": name,
            "kind": "http",
            "status": status,
            "input_schema": input_schema,
            "http": {
                "method": normalized_method,
                "url": url,
                "timeout_ms": timeout_ms,
                "headers": headers or {},
            },
        }
        if description is not None:
            payload["description"] = description
        if slug is not None:
            payload["slug"] = slug
        return self.create(payload)

    def update(
        self,
        tool_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._client.request(
            "PUT",
            f"/tools/{normalize_tool_id(tool_id)}",
            json=payload,
        )

    def delete(self, tool_id: str) -> None:
        self._client.request(
            "DELETE",
            f"/tools/{normalize_tool_id(tool_id)}",
        )
