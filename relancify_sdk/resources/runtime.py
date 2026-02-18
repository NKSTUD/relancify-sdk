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

    def build_websocket_url(
        self, session_id: str, access_token: Optional[str] = None
    ) -> str:
        ws_base = self._client.base_url
        if ws_base.startswith("https://"):
            ws_base = "wss://" + ws_base[len("https://") :]
        elif ws_base.startswith("http://"):
            ws_base = "ws://" + ws_base[len("http://") :]

        if access_token:
            token = quote(access_token, safe="")
            return f"{ws_base}/runtime/sessions/{session_id}?access_token={token}"
        return f"{ws_base}/runtime/sessions/{session_id}"
