from typing import Any, Dict, Optional
from urllib.parse import quote

from relancify_sdk.http import HttpClient


class RuntimeResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._client.request("GET", f"/runtime/sessions/{session_id}")

    def close_session(self, session_id: str) -> Dict[str, Any]:
        return self._client.request("DELETE", f"/runtime/sessions/{session_id}")

    def create_connect_token(self, session_id: str) -> Dict[str, Any]:
        return self._client.request("POST", f"/runtime/sessions/{session_id}/connect-token")

    def build_websocket_url(
        self,
        session_id: str,
        access_token: Optional[str] = None,
        connect_token: Optional[str] = None,
    ) -> str:
        ws_base = self._client.base_url
        if ws_base.startswith("https://"):
            ws_base = "wss://" + ws_base[len("https://") :]
        elif ws_base.startswith("http://"):
            ws_base = "ws://" + ws_base[len("http://") :]

        token_value = connect_token or access_token
        if token_value:
            token = quote(token_value, safe="")
            return f"{ws_base}/runtime/sessions/{session_id}?access_token={token}"
        return f"{ws_base}/runtime/sessions/{session_id}"
