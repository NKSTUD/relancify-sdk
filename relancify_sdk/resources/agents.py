import asyncio
import json
import re
from typing import Any, Dict, Iterator, List, Optional
from uuid import UUID, uuid4

from agents import Agent, ModelSettings, RunConfig, Runner

from relancify_sdk.http import HttpClient
from relancify_sdk.local_agents import RelancifyAgentModel, normalize_local_tools


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


class AgentsResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        return self._client.request("GET", "/agents")

    def get(self, agent_id: str) -> Dict[str, Any]:
        return self._client.request("GET", f"/agents/{_to_path_agent_id(agent_id)}")

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.request("POST", "/agents", json=payload)

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
                    yield {
                        "event": event_name,
                        "data": json.loads("\n".join(data_lines)),
                    }
                event_name = "message"
                data_lines = []
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())

        if data_lines:
            yield {
                "event": event_name,
                "data": json.loads("\n".join(data_lines)),
            }

    def run_local(
        self,
        agent_id: str,
        *,
        input: Any,
        tools: Optional[List[Any]] = None,
        max_turns: int = 10,
    ) -> Any:
        """Run an Agents SDK loop locally so Python tools stay in client code."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.run_local_async(
                    agent_id,
                    input=input,
                    tools=tools,
                    max_turns=max_turns,
                )
            )
        raise RuntimeError(
            "run_local() cannot run inside an active event loop; "
            "use await run_local_async() instead"
        )

    async def run_local_async(
        self,
        agent_id: str,
        *,
        input: Any,
        tools: Optional[List[Any]] = None,
        max_turns: int = 10,
    ) -> Any:
        """Asynchronously run an Agents SDK loop with client-local Python tools."""
        normalized_agent_id = _to_path_agent_id(agent_id)
        config = await asyncio.to_thread(self.get, normalized_agent_id)
        if config.get("modality") != "text":
            raise ValueError("Local runs are only available for text agents")

        prompt = config.get("prompt")
        llm = config.get("llm")
        if not isinstance(prompt, dict) or not str(prompt.get("system") or "").strip():
            raise ValueError("Agent prompt.system is required")
        if not isinstance(llm, dict) or not str(llm.get("model") or "").strip():
            raise ValueError("Agent llm.model is required")

        local_agent = Agent(
            name=str(config.get("name") or "Relancify agent"),
            instructions=str(prompt["system"]),
            model=RelancifyAgentModel(
                client=self._client,
                agent_id=normalized_agent_id,
            ),
            model_settings=_build_model_settings(llm),
            tools=normalize_local_tools(tools),
        )
        return await Runner.run(
            local_agent,
            input,
            max_turns=max(1, int(max_turns)),
            run_config=RunConfig(
                tracing_disabled=True,
                trace_include_sensitive_data=False,
                workflow_name="Relancify local text agent",
            ),
        )

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


def _build_model_settings(llm: Dict[str, Any]) -> ModelSettings:
    return ModelSettings(
        temperature=_optional_float(llm.get("temperature")),
        top_p=_optional_float(llm.get("top_p")),
        presence_penalty=_optional_float(llm.get("presence_penalty")),
        frequency_penalty=_optional_float(llm.get("frequency_penalty")),
        max_tokens=_optional_int(llm.get("max_output_tokens")),
    )


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)
