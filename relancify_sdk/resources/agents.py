import json
import re
from collections.abc import Callable
from typing import Any, Dict, Iterator, List, Optional
from uuid import UUID, uuid4

from relancify_sdk.http import AsyncHttpClient, HttpClient
from relancify_sdk.resources.tools import normalize_tool_id

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


def _to_request_id(value: Optional[str]) -> str:
    if value is None:
        return str(uuid4())
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Invalid request_id. Expected a UUID.") from exc


def _to_stream_text_event(event_name: str, data_lines: List[str]) -> Dict[str, Any]:
    data = json.loads("\n".join(data_lines))
    if event_name == "error":
        message = (
            data.get("message")
            if isinstance(data, dict)
            else "Text agent stream failed"
        )
        raise RuntimeError(str(message))
    return {"event": event_name, "data": data}


class AgentsResource:
    def __init__(
        self,
        client: HttpClient,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self._client = client
        self._on_change = on_change

    def list(self) -> List[Dict[str, Any]]:
        return self._client.request("GET", "/agents")

    def get(self, agent_id: str) -> Dict[str, Any]:
        return self._client.request("GET", f"/agents/{_to_path_agent_id(agent_id)}")

    def create(
        self,
        payload: Optional[Dict[str, Any]] = None,
        *,
        name: Optional[str] = None,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        status: str = "draft",
        rag_enabled: bool = True,
        temperature: Optional[float] = None,
        session: Optional[Dict[str, Any]] = None,
        tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if payload is not None:
            if name is not None or instructions is not None or model is not None:
                raise TypeError(
                    "Pass either a complete payload or named text-agent fields, not both"
                )
            return self._client.request("POST", "/agents", json=payload)
        if name is None or instructions is None or model is None:
            raise TypeError("name, instructions, and model are required")
        return self.create_text(
            name=name,
            instructions=instructions,
            model=model,
            status=status,
            rag_enabled=rag_enabled,
            temperature=temperature,
            session=session,
            tools=tools,
        )

    def create_text(
        self,
        *,
        name: str,
        instructions: str,
        model: str,
        status: str = "draft",
        rag_enabled: bool = True,
        temperature: Optional[float] = None,
        session: Optional[Dict[str, Any]] = None,
        tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a managed text agent without exposing provider configuration."""
        llm: Dict[str, Any] = {"model": model}
        if temperature is not None:
            llm["temperature"] = temperature

        payload: Dict[str, Any] = {
            "name": name,
            "status": status,
            "modality": "text",
            "prompt": {
                "system": instructions,
                "rag_enabled": rag_enabled,
            },
            "llm": llm,
        }
        if session is not None:
            payload["session"] = session
        if tools:
            payload["tools"] = [
                {
                    "id": normalize_tool_id(tool_id),
                    "required": False,
                }
                for tool_id in tools
            ]

        return self.create(payload)

    def run_text(
        self,
        agent_id: str,
        *,
        input: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run one managed text turn, optionally continuing a conversation."""
        payload: Dict[str, Any] = {
            "request_id": _to_request_id(request_id),
            "input": input,
        }
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id

        return self._client.request(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runs",
            json=payload,
        )

    def stream_text(
        self,
        agent_id: str,
        *,
        input: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield stable SSE events for one hosted text agent turn."""
        payload: Dict[str, Any] = {
            "request_id": _to_request_id(request_id),
            "input": input,
        }
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id

        event_name = "message"
        data_lines: List[str] = []
        for line in self._client.stream_lines(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runs/stream",
            json=payload,
        ):
            if not line:
                if data_lines:
                    yield _to_stream_text_event(event_name, data_lines)
                event_name = "message"
                data_lines = []
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())

        if data_lines:
            yield _to_stream_text_event(event_name, data_lines)

    def update(self, agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized_agent_id = _to_path_agent_id(agent_id)
        response = self._client.request(
            "PUT",
            f"/agents/{normalized_agent_id}",
            json=payload,
        )
        self._notify_change(normalized_agent_id)
        return response

    def publish(self, agent_id: str) -> Dict[str, Any]:
        normalized_agent_id = _to_path_agent_id(agent_id)
        response = self._client.request(
            "POST",
            f"/agents/{normalized_agent_id}/publish",
        )
        self._notify_change(normalized_agent_id)
        return response

    def delete(self, agent_id: str) -> None:
        normalized_agent_id = _to_path_agent_id(agent_id)
        self._client.request("DELETE", f"/agents/{normalized_agent_id}")
        self._notify_change(normalized_agent_id)

    def create_runtime_session(self, agent_id: str) -> Dict[str, Any]:
        return self._client.request(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runtime/session",
        )

    def _notify_change(self, agent_id: str) -> None:
        if self._on_change is not None:
            self._on_change(agent_id)


class AsyncAgentsResource:
    def __init__(
        self,
        client: AsyncHttpClient,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self._client = client
        self._on_change = on_change

    async def list(self) -> List[Dict[str, Any]]:
        return await self._client.request("GET", "/agents")

    async def get(self, agent_id: str) -> Dict[str, Any]:
        return await self._client.request(
            "GET",
            f"/agents/{_to_path_agent_id(agent_id)}",
        )

    async def create(
        self,
        payload: Optional[Dict[str, Any]] = None,
        *,
        name: Optional[str] = None,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        status: str = "draft",
        rag_enabled: bool = True,
        temperature: Optional[float] = None,
        session: Optional[Dict[str, Any]] = None,
        tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if payload is None:
            if name is None or instructions is None or model is None:
                raise TypeError("name, instructions, and model are required")
            llm: Dict[str, Any] = {"model": model}
            if temperature is not None:
                llm["temperature"] = temperature
            payload = {
                "name": name,
                "status": status,
                "modality": "text",
                "prompt": {
                    "system": instructions,
                    "rag_enabled": rag_enabled,
                },
                "llm": llm,
            }
            if session is not None:
                payload["session"] = session
            if tools:
                payload["tools"] = [
                    {
                        "id": normalize_tool_id(tool_id),
                        "required": False,
                    }
                    for tool_id in tools
                ]
        elif name is not None or instructions is not None or model is not None:
            raise TypeError(
                "Pass either a complete payload or named text-agent fields, not both"
            )
        return await self._client.request("POST", "/agents", json=payload)

    async def update(
        self,
        agent_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized_agent_id = _to_path_agent_id(agent_id)
        response = await self._client.request(
            "PUT",
            f"/agents/{normalized_agent_id}",
            json=payload,
        )
        self._notify_change(normalized_agent_id)
        return response

    async def publish(self, agent_id: str) -> Dict[str, Any]:
        normalized_agent_id = _to_path_agent_id(agent_id)
        response = await self._client.request(
            "POST",
            f"/agents/{normalized_agent_id}/publish",
        )
        self._notify_change(normalized_agent_id)
        return response

    async def delete(self, agent_id: str) -> None:
        normalized_agent_id = _to_path_agent_id(agent_id)
        await self._client.request(
            "DELETE",
            f"/agents/{normalized_agent_id}",
        )
        self._notify_change(normalized_agent_id)

    def _notify_change(self, agent_id: str) -> None:
        if self._on_change is not None:
            self._on_change(agent_id)
