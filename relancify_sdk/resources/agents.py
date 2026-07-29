import asyncio
import json
import re
from collections.abc import Callable
from typing import Any, Dict, Iterator, List, Optional
from uuid import UUID, uuid4

from agents import Agent, ModelSettings, RunConfig, Runner

from relancify_sdk.http import AsyncHttpClient, HttpClient
from relancify_sdk.local_agents import RelancifyAgentModel, normalize_local_tools
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

    def run_local(
        self,
        agent_id: str,
        *,
        input: Any,
        tools: Optional[List[Any]] = None,
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        agent_hooks: Any = None,
        run_hooks: Any = None,
        context: Any = None,
        session: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
        run_config: Optional[RunConfig] = None,
        error_handlers: Any = None,
        previous_response_id: Optional[str] = None,
        auto_previous_response_id: bool = False,
        conversation_id: Optional[str] = None,
        max_turns: int = 10,
    ) -> Any:
        """Run a native Agents SDK loop while inference stays managed by Relancify."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.run_local_async(
                    agent_id,
                    input=input,
                    tools=tools,
                    output_type=output_type,
                    handoffs=handoffs,
                    input_guardrails=input_guardrails,
                    output_guardrails=output_guardrails,
                    agent_hooks=agent_hooks,
                    run_hooks=run_hooks,
                    context=context,
                    session=session,
                    model_settings=model_settings,
                    prompt=prompt,
                    run_config=run_config,
                    error_handlers=error_handlers,
                    previous_response_id=previous_response_id,
                    auto_previous_response_id=auto_previous_response_id,
                    conversation_id=conversation_id,
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
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        agent_hooks: Any = None,
        run_hooks: Any = None,
        context: Any = None,
        session: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
        run_config: Optional[RunConfig] = None,
        error_handlers: Any = None,
        previous_response_id: Optional[str] = None,
        auto_previous_response_id: bool = False,
        conversation_id: Optional[str] = None,
        max_turns: int = 10,
    ) -> Any:
        """Asynchronously run a native Agents SDK loop through Relancify."""
        local_agent = await self.build_local_agent_async(
            agent_id,
            tools=tools,
            output_type=output_type,
            handoffs=handoffs,
            input_guardrails=input_guardrails,
            output_guardrails=output_guardrails,
            hooks=agent_hooks,
            model_settings=model_settings,
            prompt=prompt,
        )
        effective_run_config = run_config or RunConfig(
            tracing_disabled=True,
            trace_include_sensitive_data=False,
            workflow_name="Relancify local text agent",
        )
        return await Runner.run(
            local_agent,
            input,
            context=context,
            max_turns=max(1, int(max_turns)),
            hooks=run_hooks,
            run_config=effective_run_config,
            error_handlers=error_handlers,
            previous_response_id=previous_response_id,
            auto_previous_response_id=auto_previous_response_id,
            conversation_id=conversation_id,
            session=session,
        )

    def build_local_agent(
        self,
        agent_id: str,
        *,
        tools: Optional[List[Any]] = None,
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        hooks: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
    ) -> Agent:
        """Build an Agents SDK Agent backed by one managed Relancify model."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.build_local_agent_async(
                    agent_id,
                    tools=tools,
                    output_type=output_type,
                    handoffs=handoffs,
                    input_guardrails=input_guardrails,
                    output_guardrails=output_guardrails,
                    hooks=hooks,
                    model_settings=model_settings,
                    prompt=prompt,
                )
            )
        raise RuntimeError(
            "build_local_agent() cannot run inside an active event loop; "
            "use await build_local_agent_async() instead"
        )

    async def build_local_agent_async(
        self,
        agent_id: str,
        *,
        tools: Optional[List[Any]] = None,
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        hooks: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
    ) -> Agent:
        """Asynchronously build a composable local Agents SDK Agent."""
        normalized_agent_id = _to_path_agent_id(agent_id)
        config = await asyncio.to_thread(self.get, normalized_agent_id)
        if config.get("modality") != "text":
            raise ValueError("Local runs are only available for text agents")

        prompt_config = config.get("prompt")
        llm = config.get("llm")
        if (
            not isinstance(prompt_config, dict)
            or not str(prompt_config.get("system") or "").strip()
        ):
            raise ValueError("Agent prompt.system is required")
        if not isinstance(llm, dict) or not str(llm.get("model") or "").strip():
            raise ValueError("Agent llm.model is required")

        configured_settings = _build_model_settings(llm)
        return Agent(
            name=str(config.get("name") or "Relancify agent"),
            instructions=str(prompt_config["system"]),
            prompt=prompt,
            handoffs=list(handoffs or []),
            model=RelancifyAgentModel(
                client=self._client,
                agent_id=normalized_agent_id,
            ),
            model_settings=configured_settings.resolve(model_settings),
            tools=normalize_local_tools(tools),
            input_guardrails=list(input_guardrails or []),
            output_guardrails=list(output_guardrails or []),
            output_type=output_type,
            hooks=hooks,
        )

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

    def normalize_runtime_event(
        self, agent_id: str, event: Dict[str, Any]
    ) -> Dict[str, Any]:
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
