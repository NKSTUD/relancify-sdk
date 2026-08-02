from typing import Any, Dict, Optional
from urllib.parse import quote

from relancify_sdk.http import AsyncHttpClient, HttpClient
from relancify_sdk.resources._ids import normalize_uuid_path
from relancify_sdk.resources.agents import _to_path_agent_id


class RuntimeResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def create_session(self, agent_id: str) -> Dict[str, Any]:
        return self._client.request(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runtime/session",
        )

    def get_session(self, session_id: str) -> Dict[str, Any]:
        normalized_id = normalize_uuid_path(session_id, field_name="session_id")
        return self._client.request("GET", f"/runtime/sessions/{normalized_id}")

    def close_session(self, session_id: str) -> Dict[str, Any]:
        normalized_id = normalize_uuid_path(session_id, field_name="session_id")
        return self._client.request("DELETE", f"/runtime/sessions/{normalized_id}")

    def create_connect_token(self, session_id: str) -> Dict[str, Any]:
        normalized_id = normalize_uuid_path(session_id, field_name="session_id")
        return self._client.request(
            "POST",
            f"/runtime/sessions/{normalized_id}/connect-token",
        )

    def build_websocket_url(
        self,
        session_id: str,
        access_token: Optional[str] = None,
        connect_token: Optional[str] = None,
    ) -> str:
        normalized_id = normalize_uuid_path(session_id, field_name="session_id")
        ws_base = self._client.base_url
        if ws_base.startswith("https://"):
            ws_base = "wss://" + ws_base[len("https://") :]
        elif ws_base.startswith("http://"):
            ws_base = "ws://" + ws_base[len("http://") :]

        token_value = connect_token or access_token
        if token_value:
            token = quote(token_value, safe="")
            return f"{ws_base}/runtime/sessions/{normalized_id}?access_token={token}"
        return f"{ws_base}/runtime/sessions/{normalized_id}"


class AsyncRuntimeResource:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def create_session(self, agent_id: str) -> Dict[str, Any]:
        return await self._client.request(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runtime/session",
        )

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        normalized_id = normalize_uuid_path(session_id, field_name="session_id")
        return await self._client.request("GET", f"/runtime/sessions/{normalized_id}")

    async def close_session(self, session_id: str) -> Dict[str, Any]:
        normalized_id = normalize_uuid_path(session_id, field_name="session_id")
        return await self._client.request(
            "DELETE",
            f"/runtime/sessions/{normalized_id}",
        )

    async def create_connect_token(self, session_id: str) -> Dict[str, Any]:
        normalized_id = normalize_uuid_path(session_id, field_name="session_id")
        return await self._client.request(
            "POST",
            f"/runtime/sessions/{normalized_id}/connect-token",
        )

    def build_websocket_url(
        self,
        session_id: str,
        access_token: Optional[str] = None,
        connect_token: Optional[str] = None,
    ) -> str:
        normalized_id = normalize_uuid_path(session_id, field_name="session_id")
        ws_base = self._client.base_url
        if ws_base.startswith("https://"):
            ws_base = "wss://" + ws_base[len("https://") :]
        elif ws_base.startswith("http://"):
            ws_base = "ws://" + ws_base[len("http://") :]

        token_value = connect_token or access_token
        if token_value:
            token = quote(token_value, safe="")
            return f"{ws_base}/runtime/sessions/{normalized_id}?access_token={token}"
        return f"{ws_base}/runtime/sessions/{normalized_id}"
