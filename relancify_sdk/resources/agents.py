import json
import re
import warnings
from collections.abc import Callable
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional
from uuid import UUID, uuid4

from relancify_sdk.http import AsyncHttpClient, HttpClient
from relancify_sdk.resources.tools import normalize_capability_id
from relancify_sdk.skills import Skill, serialize_skills

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


def _to_stream_text_event(
    event_name: str,
    data_lines: List[str],
    *,
    raise_on_error: bool,
) -> Dict[str, Any]:
    data = json.loads("\n".join(data_lines))
    if event_name == "error" and raise_on_error:
        message = (
            data.get("message")
            if isinstance(data, dict)
            else "Text agent stream failed"
        )
        raise RuntimeError(str(message))
    return {"event": event_name, "data": data}


def _build_agent_payload(
    *,
    name: str,
    interaction_mode: str,
    instructions: str,
    model: Optional[str],
    llm_model: Optional[str],
    stt_model: Optional[str],
    tts_model: Optional[str],
    voice: Optional[str],
    language: Optional[str],
    first_message: Optional[str],
    status: str,
    rag_enabled: bool,
    temperature: Optional[float],
    session: Optional[Dict[str, Any]],
    capabilities: Optional[List[str]],
    tools: Optional[List[str]],
    skills: Optional[List[Skill | Dict[str, Any]]],
    runtime: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    mode = str(interaction_mode or "").strip().lower()
    if mode not in {"chat", "voice"}:
        raise ValueError("interaction_mode must be 'chat' or 'voice'")
    if capabilities is not None and tools is not None:
        raise TypeError("Pass capabilities, not both capabilities and tools")
    capability_ids = capabilities if capabilities is not None else tools

    normalized_session = dict(session or {})
    if language is not None:
        normalized_session["language"] = language
    if first_message is not None:
        normalized_session["first_message"] = first_message

    if mode == "chat":
        if llm_model is not None:
            raise TypeError("Use model for chat agents; llm_model is for voice agents")
        if any(value is not None for value in (stt_model, tts_model, voice)):
            raise TypeError("Chat agents cannot define STT, TTS, or voice fields")
        selected_llm_model = str(model or "").strip()
        if not selected_llm_model:
            raise TypeError("model is required for chat agents")
        backend_mode = "text"
    else:
        if model is not None:
            raise TypeError("Use llm_model for voice agents")
        selected_llm_model = str(llm_model or "").strip()
        missing = [
            field
            for field, value in (
                ("llm_model", selected_llm_model),
                ("stt_model", stt_model),
                ("tts_model", tts_model),
                ("voice", voice),
            )
            if not str(value or "").strip()
        ]
        if missing:
            raise TypeError(
                f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} "
                "required for voice agents"
            )
        backend_mode = "voice"

    llm: Dict[str, Any] = {"model": selected_llm_model}
    if temperature is not None:
        llm["temperature"] = temperature

    payload: Dict[str, Any] = {
        "name": name,
        "status": status,
        "modality": backend_mode,
        "prompt": {"system": instructions, "rag_enabled": rag_enabled},
        "llm": llm,
    }
    if normalized_session:
        payload["session"] = normalized_session
    if mode == "voice":
        payload["stt"] = {"model": str(stt_model).strip()}
        payload["tts"] = {
            "model": str(tts_model).strip(),
            "voice_id": str(voice).strip(),
        }
        if language is not None:
            payload["stt"]["language"] = language
            payload["tts"]["language"] = language
        if runtime:
            if runtime.get("provider") is not None:
                raise TypeError(
                    "runtime.provider is managed by Relancify; "
                    "pass only LiveKit runtime options"
                )
            payload["runtime"] = dict(runtime)
    elif runtime is not None:
        raise TypeError("Chat agents cannot define voice runtime options")

    if skills:
        payload["skills"] = serialize_skills(skills)
    if capability_ids:
        payload["tools"] = [
            {"id": normalize_capability_id(capability_id), "required": False}
            for capability_id in capability_ids
        ]
    return payload


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
        interaction_mode: str = "chat",
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        llm_model: Optional[str] = None,
        stt_model: Optional[str] = None,
        tts_model: Optional[str] = None,
        voice: Optional[str] = None,
        language: Optional[str] = None,
        first_message: Optional[str] = None,
        status: str = "draft",
        rag_enabled: bool = True,
        temperature: Optional[float] = None,
        session: Optional[Dict[str, Any]] = None,
        capabilities: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        skills: Optional[List[Skill | Dict[str, Any]]] = None,
        runtime: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if payload is not None:
            if (
                interaction_mode != "chat"
                or status != "draft"
                or rag_enabled is not True
            ):
                raise TypeError(
                    "Pass either a complete payload or named agent fields, not both"
                )
            if any(
                value is not None
                for value in (
                    name,
                    instructions,
                    model,
                    llm_model,
                    stt_model,
                    tts_model,
                    voice,
                    language,
                    first_message,
                    temperature,
                    session,
                    capabilities,
                    tools,
                    skills,
                    runtime,
                )
            ):
                raise TypeError(
                    "Pass either a complete payload or named agent fields, not both"
                )
            return self._client.request("POST", "/agents", json=payload)
        if name is None or instructions is None:
            raise TypeError("name and instructions are required")
        compiled_payload = _build_agent_payload(
            name=name,
            interaction_mode=interaction_mode,
            instructions=instructions,
            model=model,
            llm_model=llm_model,
            stt_model=stt_model,
            tts_model=tts_model,
            voice=voice,
            language=language,
            first_message=first_message,
            status=status,
            rag_enabled=rag_enabled,
            temperature=temperature,
            session=session,
            capabilities=capabilities,
            tools=tools,
            skills=skills,
            runtime=runtime,
        )
        return self._client.request("POST", "/agents", json=compiled_payload)

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
        skills: Optional[List[Skill | Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Deprecated compatibility alias for ``create(interaction_mode='chat')``."""
        warnings.warn(
            "agents.create_text() is deprecated; use agents.create() with "
            "interaction_mode='chat'",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.create(
            name=name,
            interaction_mode="chat",
            instructions=instructions,
            model=model,
            status=status,
            rag_enabled=rag_enabled,
            temperature=temperature,
            session=session,
            tools=tools,
            skills=skills,
        )

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
        yield from self._stream_run_events(
            agent_id,
            input=input,
            conversation_id=conversation_id,
            request_id=request_id,
            raise_on_error=True,
        )

    def stream_run(
        self,
        agent_id: str,
        *,
        input: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield hosted events without translating error events into exceptions."""
        yield from self._stream_run_events(
            agent_id,
            input=input,
            conversation_id=conversation_id,
            request_id=request_id,
            raise_on_error=False,
        )

    def _stream_run_events(
        self,
        agent_id: str,
        *,
        input: str,
        conversation_id: Optional[str],
        request_id: Optional[str],
        raise_on_error: bool,
    ) -> Iterator[Dict[str, Any]]:
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
                    yield _to_stream_text_event(
                        event_name,
                        data_lines,
                        raise_on_error=raise_on_error,
                    )
                event_name = "message"
                data_lines = []
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())

        if data_lines:
            yield _to_stream_text_event(
                event_name,
                data_lines,
                raise_on_error=raise_on_error,
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
        warnings.warn(
            "agents.create_runtime_session() is deprecated; "
            "use runtime.create_session()",
            DeprecationWarning,
            stacklevel=2,
        )
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
        interaction_mode: str = "chat",
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        llm_model: Optional[str] = None,
        stt_model: Optional[str] = None,
        tts_model: Optional[str] = None,
        voice: Optional[str] = None,
        language: Optional[str] = None,
        first_message: Optional[str] = None,
        status: str = "draft",
        rag_enabled: bool = True,
        temperature: Optional[float] = None,
        session: Optional[Dict[str, Any]] = None,
        capabilities: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        skills: Optional[List[Skill | Dict[str, Any]]] = None,
        runtime: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if payload is None:
            if name is None or instructions is None:
                raise TypeError("name and instructions are required")
            payload = _build_agent_payload(
                name=name,
                interaction_mode=interaction_mode,
                instructions=instructions,
                model=model,
                llm_model=llm_model,
                stt_model=stt_model,
                tts_model=tts_model,
                voice=voice,
                language=language,
                first_message=first_message,
                status=status,
                rag_enabled=rag_enabled,
                temperature=temperature,
                session=session,
                capabilities=capabilities,
                tools=tools,
                skills=skills,
                runtime=runtime,
            )
        elif (
            interaction_mode != "chat"
            or status != "draft"
            or rag_enabled is not True
            or any(
                value is not None
                for value in (
                    name,
                    instructions,
                    model,
                    llm_model,
                    stt_model,
                    tts_model,
                    voice,
                    language,
                    first_message,
                    temperature,
                    session,
                    capabilities,
                    tools,
                    skills,
                    runtime,
                )
            )
        ):
            raise TypeError(
                "Pass either a complete payload or named agent fields, not both"
            )
        return await self._client.request("POST", "/agents", json=payload)

    async def create_text(
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
        skills: Optional[List[Skill | Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        warnings.warn(
            "agents.create_text() is deprecated; use agents.create() with "
            "interaction_mode='chat'",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.create(
            name=name,
            interaction_mode="chat",
            instructions=instructions,
            model=model,
            status=status,
            rag_enabled=rag_enabled,
            temperature=temperature,
            session=session,
            tools=tools,
            skills=skills,
        )

    async def run_text(
        self,
        agent_id: str,
        *,
        input: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "request_id": _to_request_id(request_id),
            "input": input,
        }
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        return await self._client.request(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runs",
            json=payload,
        )

    async def stream_run(
        self,
        agent_id: str,
        *,
        input: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "request_id": _to_request_id(request_id),
            "input": input,
        }
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id

        event_name = "message"
        data_lines: List[str] = []
        async for line in self._client.stream_lines(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runs/stream",
            json=payload,
        ):
            if not line:
                if data_lines:
                    yield _to_stream_text_event(
                        event_name,
                        data_lines,
                        raise_on_error=False,
                    )
                event_name = "message"
                data_lines = []
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            yield _to_stream_text_event(
                event_name,
                data_lines,
                raise_on_error=False,
            )

    async def stream_text(
        self,
        agent_id: str,
        *,
        input: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Deprecated hosted stream that raises when an error event arrives."""
        async for event in self.stream_run(
            agent_id,
            input=input,
            conversation_id=conversation_id,
            request_id=request_id,
        ):
            if event["event"] == "error":
                data = event.get("data")
                message = (
                    data.get("message")
                    if isinstance(data, dict)
                    else "Text agent stream failed"
                )
                raise RuntimeError(str(message))
            yield event

    async def create_runtime_session(self, agent_id: str) -> Dict[str, Any]:
        warnings.warn(
            "agents.create_runtime_session() is deprecated; "
            "use runtime.create_session()",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self._client.request(
            "POST",
            f"/agents/{_to_path_agent_id(agent_id)}/runtime/session",
        )

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
