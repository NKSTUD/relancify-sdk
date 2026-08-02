import re
from typing import Any, Dict, List, Optional

from relancify_sdk.http import AsyncHttpClient, HttpClient

TOOL_PUBLIC_ID_RE = re.compile(
    r"^tool_[0-9a-f]{8}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{12}$"
)
INTEGRATION_PUBLIC_ID_RE = re.compile(
    r"^intg_[0-9a-f]{8}-"
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


def normalize_capability_id(value: str) -> str:
    raw = str(value or "").strip()
    if TOOL_PUBLIC_ID_RE.fullmatch(raw) or INTEGRATION_PUBLIC_ID_RE.fullmatch(raw):
        return raw
    raise ValueError(
        "Invalid capability ID. Expected tool_<uuid> or intg_<uuid>."
    )


def _mcp_http_payload(
    *,
    name: str,
    server_url: str,
    description: Optional[str] = None,
    slug: Optional[str] = None,
    transport_type: str = "auto",
    headers: Optional[Dict[str, str]] = None,
    allowed_tools: Optional[List[str]] = None,
    timeout_seconds: float = 5.0,
    read_timeout_seconds: float = 300.0,
    client_session_timeout_seconds: float = 5.0,
    status: str = "active",
) -> Dict[str, Any]:
    normalized_transport = str(transport_type or "auto").strip().lower()
    if normalized_transport not in {"auto", "sse", "streamable_http"}:
        raise ValueError(
            "Invalid MCP HTTP transport. Expected auto, sse, or streamable_http."
        )
    payload: Dict[str, Any] = {
        "name": name,
        "kind": "mcp",
        "status": status,
        "mcp": {
            "transport": "http",
            "allowed_tools": list(allowed_tools or []),
            "client_session_timeout_seconds": client_session_timeout_seconds,
            "http": {
                "server_url": server_url,
                "transport_type": normalized_transport,
                "headers": dict(headers or {}),
                "timeout_seconds": timeout_seconds,
                "read_timeout_seconds": read_timeout_seconds,
            },
        },
    }
    if description is not None:
        payload["description"] = description
    if slug is not None:
        payload["slug"] = slug
    return payload


def _mcp_stdio_payload(
    *,
    name: str,
    command: str,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
    description: Optional[str] = None,
    slug: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    client_session_timeout_seconds: float = 5.0,
    status: str = "active",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": name,
        "kind": "mcp",
        "status": status,
        "mcp": {
            "transport": "stdio",
            "allowed_tools": list(allowed_tools or []),
            "client_session_timeout_seconds": client_session_timeout_seconds,
            "stdio": {
                "command": command,
                "args": list(args or []),
                "env": dict(env or {}),
                "cwd": cwd,
            },
        },
    }
    if description is not None:
        payload["description"] = description
    if slug is not None:
        payload["slug"] = slug
    return payload


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

    def create_mcp_http(
        self,
        *,
        name: str,
        server_url: str,
        description: Optional[str] = None,
        slug: Optional[str] = None,
        transport_type: str = "auto",
        headers: Optional[Dict[str, str]] = None,
        allowed_tools: Optional[List[str]] = None,
        timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 300.0,
        client_session_timeout_seconds: float = 5.0,
        status: str = "active",
    ) -> Dict[str, Any]:
        """Register a remote MCP server for managed Relancify runtimes."""
        return self.create(
            _mcp_http_payload(
                name=name,
                server_url=server_url,
                description=description,
                slug=slug,
                transport_type=transport_type,
                headers=headers,
                allowed_tools=allowed_tools,
                timeout_seconds=timeout_seconds,
                read_timeout_seconds=read_timeout_seconds,
                client_session_timeout_seconds=client_session_timeout_seconds,
                status=status,
            )
        )

    def create_mcp_stdio(
        self,
        *,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        description: Optional[str] = None,
        slug: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        client_session_timeout_seconds: float = 5.0,
        status: str = "active",
    ) -> Dict[str, Any]:
        """Register an MCP stdio definition for customer-owned runtimes."""
        return self.create(
            _mcp_stdio_payload(
                name=name,
                command=command,
                args=args,
                env=env,
                cwd=cwd,
                description=description,
                slug=slug,
                allowed_tools=allowed_tools,
                client_session_timeout_seconds=client_session_timeout_seconds,
                status=status,
            )
        )

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


class AsyncToolsResource:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self) -> List[Dict[str, Any]]:
        return await self._client.request("GET", "/tools/")

    async def get(self, tool_id: str) -> Dict[str, Any]:
        return await self._client.request(
            "GET",
            f"/tools/{normalize_tool_id(tool_id)}",
        )

    async def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.request("POST", "/tools/", json=payload)

    async def create_http(
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
        return await self.create(payload)

    async def create_mcp_http(
        self,
        *,
        name: str,
        server_url: str,
        description: Optional[str] = None,
        slug: Optional[str] = None,
        transport_type: str = "auto",
        headers: Optional[Dict[str, str]] = None,
        allowed_tools: Optional[List[str]] = None,
        timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 300.0,
        client_session_timeout_seconds: float = 5.0,
        status: str = "active",
    ) -> Dict[str, Any]:
        return await self.create(
            _mcp_http_payload(
                name=name,
                server_url=server_url,
                description=description,
                slug=slug,
                transport_type=transport_type,
                headers=headers,
                allowed_tools=allowed_tools,
                timeout_seconds=timeout_seconds,
                read_timeout_seconds=read_timeout_seconds,
                client_session_timeout_seconds=client_session_timeout_seconds,
                status=status,
            )
        )

    async def create_mcp_stdio(
        self,
        *,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        description: Optional[str] = None,
        slug: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        client_session_timeout_seconds: float = 5.0,
        status: str = "active",
    ) -> Dict[str, Any]:
        return await self.create(
            _mcp_stdio_payload(
                name=name,
                command=command,
                args=args,
                env=env,
                cwd=cwd,
                description=description,
                slug=slug,
                allowed_tools=allowed_tools,
                client_session_timeout_seconds=client_session_timeout_seconds,
                status=status,
            )
        )

    async def update(
        self,
        tool_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return await self._client.request(
            "PUT",
            f"/tools/{normalize_tool_id(tool_id)}",
            json=payload,
        )

    async def delete(self, tool_id: str) -> None:
        await self._client.request(
            "DELETE",
            f"/tools/{normalize_tool_id(tool_id)}",
        )
