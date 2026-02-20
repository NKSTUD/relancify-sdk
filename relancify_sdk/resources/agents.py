import re
from typing import Any, Dict, List, Optional

from relancify_sdk.http import HttpClient


AGENT_PUBLIC_ID_RE = re.compile(
    r"^ag_[0-9a-f]{8}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{12}$"
)


def _to_path_agent_id(value: str) -> str:
    raw = str(value or "").strip()
    if not AGENT_PUBLIC_ID_RE.fullmatch(raw):
        raise ValueError("Invalid agent_id. Expected format ag_<uuid>.")
    return raw


class AgentsResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        return self._client.request("GET", "/agents")

    def get(self, agent_id: str) -> Dict[str, Any]:
        return self._client.request("GET", f"/agents/{_to_path_agent_id(agent_id)}")

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.request("POST", "/agents", json=payload)

    def update(self, agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.request(
            "PUT",
            f"/agents/{_to_path_agent_id(agent_id)}",
            json=payload,
        )

    def publish(self, agent_id: str) -> Dict[str, Any]:
        return self._client.request("POST", f"/agents/{_to_path_agent_id(agent_id)}/publish")

    def delete(self, agent_id: str) -> None:
        self._client.request("DELETE", f"/agents/{_to_path_agent_id(agent_id)}")

    def get_provider_config(self, agent_id: str) -> Dict[str, Any]:
        return self._client.request("GET", f"/agents/{_to_path_agent_id(agent_id)}/provider")

    def create_runtime_session(self, agent_id: str) -> Dict[str, Any]:
        return self._client.request(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runtime/session",
        )

    def normalize_runtime_event(self, agent_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.request(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runtime/events/normalize",
            json={"event": event},
        )

    def compile_runtime_event(
        self,
        agent_id: str,
        *,
        event_type: str,
        event_id: Optional[str] = None,
        text: Optional[str] = None,
        audio_base64: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "type": event_type,
            "event_id": event_id,
            "text": text,
            "audio_base64": audio_base64,
            "metadata": metadata or {},
            "raw_payload": raw_payload or {},
        }
        return self._client.request(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runtime/events/compile",
            json=payload,
        )
