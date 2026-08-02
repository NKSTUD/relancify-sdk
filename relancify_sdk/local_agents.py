from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from agents import (
    CustomTool,
    FunctionTool,
    Handoff,
    ProgrammaticToolCallingTool,
    ToolSearchTool,
)
from agents.agent_output import AgentOutputSchemaBase
from agents.items import TResponseStreamEvent
from agents.models.interface import Model, ModelProvider, ModelResponse
from pydantic import BaseModel, TypeAdapter

from relancify_sdk.http import AsyncHttpClient, HttpClient

_MODEL_RESPONSE_ADAPTER = TypeAdapter(ModelResponse)
_STREAM_EVENT_ADAPTER = TypeAdapter(TResponseStreamEvent)
_HttpClient = HttpClient | AsyncHttpClient


class RelancifyModel(Model):
    """Model adapter backed by a public Relancify model key."""

    def __init__(
        self,
        *,
        client: _HttpClient,
        model_name: str,
    ) -> None:
        normalized_model_name = str(model_name or "").strip()
        if not normalized_model_name:
            raise ValueError("model_name is required")
        self._client = client
        self._model_name = normalized_model_name

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ) -> ModelResponse:
        del tracing
        payload = _compile_model_request(
            model_name=self._model_name,
            system_instructions=system_instructions,
            input=input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        response = await _request(
            self._client,
            "POST",
            "/models/responses",
            payload,
        )
        return _parse_model_response(response)

    async def stream_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ) -> AsyncIterator[Any]:
        del tracing
        payload = _compile_model_request(
            model_name=self._model_name,
            system_instructions=system_instructions,
            input=input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        async for event in _stream_model_events(
            self._client,
            "/models/responses/stream",
            payload,
        ):
            yield event


class RelancifyAgentModel(RelancifyModel):
    """Backward-compatible adapter for one registered Relancify agent."""

    def __init__(
        self,
        *,
        client: _HttpClient,
        agent_id: str,
        model_name: str = "registered-agent-model",
    ) -> None:
        super().__init__(client=client, model_name=model_name)
        self._agent_id = agent_id

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ) -> ModelResponse:
        del tracing
        payload = _compile_model_request(
            model_name=None,
            system_instructions=system_instructions,
            input=input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        response = await _request(
            self._client,
            "POST",
            f"/agents/{self._agent_id}/model/responses",
            payload,
        )
        return _parse_model_response(response)

    async def stream_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ) -> AsyncIterator[Any]:
        del tracing
        payload = _compile_model_request(
            model_name=None,
            system_instructions=system_instructions,
            input=input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        async for event in _stream_model_events(
            self._client,
            f"/agents/{self._agent_id}/model/responses/stream",
            payload,
        ):
            yield event


class RelancifyModelProvider(ModelProvider):
    """Resolve simple Agent model strings through Relancify."""

    def __init__(self, client: _HttpClient) -> None:
        self._client = client
        self._models: dict[str, RelancifyModel] = {}

    def get_model(self, model_name: str | None) -> Model:
        normalized_model_name = str(model_name or "").strip()
        if not normalized_model_name:
            raise ValueError(
                "A Relancify public model name is required, "
                'for example model="gpt-4o-mini".'
            )
        model = self._models.get(normalized_model_name)
        if model is None:
            model = RelancifyModel(
                client=self._client,
                model_name=normalized_model_name,
            )
            self._models[normalized_model_name] = model
        return model


def normalize_local_tools(tools: Optional[List[Any]]) -> List[Any]:
    normalized: List[Any] = []
    for tool in tools or []:
        if isinstance(
            tool,
            (
                CustomTool,
                FunctionTool,
                ProgrammaticToolCallingTool,
                ToolSearchTool,
            ),
        ):
            normalized.append(tool)
            continue
        if callable(tool):
            from agents import function_tool

            normalized.append(function_tool(tool))
            continue
        raise TypeError(
            "Local tools must be Python callables, FunctionTool objects, "
            "or ProgrammaticToolCallingTool objects"
        )
    return normalized


def _compile_model_request(
    *,
    model_name: str | None,
    system_instructions: str | None,
    input: Any,
    model_settings: Any,
    tools: List[Any],
    output_schema: AgentOutputSchemaBase | None,
    handoffs: List[Handoff],
    previous_response_id: str | None,
    conversation_id: str | None,
    prompt: Any,
) -> Dict[str, Any]:
    serialized_settings = _serialize_model_settings(model_settings)
    payload: Dict[str, Any] = {
        "request_id": str(uuid4()),
        "input": _to_json_value(input),
        "system_instructions": system_instructions,
        "tools": [_serialize_tool(tool) for tool in tools],
        "output_schema": _serialize_output_schema(output_schema),
        "handoffs": [_serialize_handoff(handoff) for handoff in handoffs],
        "model_settings": serialized_settings,
        "tool_choice": _to_json_value(model_settings.tool_choice),
        "parallel_tool_calls": model_settings.parallel_tool_calls,
        "previous_response_id": previous_response_id,
        "conversation_id": conversation_id,
        "prompt": _serialize_prompt(prompt),
    }
    if model_name is not None:
        payload["model"] = model_name
    return payload


def _serialize_tool(tool: Any) -> Dict[str, Any]:
    if isinstance(tool, ProgrammaticToolCallingTool):
        return {"type": "programmatic_tool_calling"}
    if isinstance(tool, ToolSearchTool):
        payload = {"type": "tool_search"}
        if tool.description is not None:
            payload["description"] = tool.description
        if tool.execution is not None:
            payload["execution"] = tool.execution
        if tool.parameters is not None:
            payload["parameters"] = _to_json_value(tool.parameters)
        return payload
    if isinstance(tool, CustomTool):
        payload = {
            "type": "custom",
            "name": tool.name,
            "description": tool.description,
            "defer_loading": tool.defer_loading,
        }
        if tool.format is not None:
            payload["format"] = _to_json_value(tool.format)
        if tool.allowed_callers is not None:
            payload["allowed_callers"] = _to_json_value(tool.allowed_callers)
        return payload
    if not isinstance(tool, FunctionTool):
        raise TypeError(
            f"Tool type {type(tool).__name__} cannot be sent through "
            "the Relancify model gateway. Use a local FunctionTool."
        )

    payload: Dict[str, Any] = {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.params_json_schema,
        "strict": tool.strict_json_schema,
        "defer_loading": tool.defer_loading,
    }
    if tool.allowed_callers is not None:
        payload["allowed_callers"] = _to_json_value(tool.allowed_callers)
    if tool.output_json_schema is not None:
        payload["output_schema"] = tool.output_json_schema
    return payload


def _serialize_output_schema(
    output_schema: Optional[AgentOutputSchemaBase],
) -> Optional[Dict[str, Any]]:
    if output_schema is None or output_schema.is_plain_text():
        return None
    return {
        "name": output_schema.name(),
        "json_schema": output_schema.json_schema(),
        "strict": output_schema.is_strict_json_schema(),
    }


def _serialize_handoff(handoff: Handoff) -> Dict[str, Any]:
    return {
        "tool_name": handoff.tool_name,
        "tool_description": handoff.tool_description,
        "input_json_schema": handoff.input_json_schema,
        "agent_name": handoff.agent_name,
        "strict": handoff.strict_json_schema,
    }


def _serialize_prompt(prompt: Any) -> Optional[Dict[str, Any]]:
    if prompt is None:
        return None
    serialized = _to_json_value(prompt)
    if not isinstance(serialized, dict):
        raise TypeError("Hosted prompt configuration must be a dictionary")
    return {str(key): value for key, value in serialized.items() if value is not None}


def _serialize_model_settings(model_settings: Any) -> Dict[str, Any]:
    serialized = model_settings.to_json_dict()
    unsupported_provider_fields = {
        field_name: serialized.get(field_name)
        for field_name in (
            "extra_query",
            "extra_body",
            "extra_headers",
            "extra_args",
        )
        if serialized.get(field_name) is not None
    }
    if unsupported_provider_fields:
        names = ", ".join(sorted(unsupported_provider_fields))
        raise ValueError(
            f"{names} cannot be used with managed Relancify models because "
            "provider-specific request overrides would bypass managed routing."
        )

    supported_fields = (
        "temperature",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
        "truncation",
        "max_tokens",
        "reasoning",
        "verbosity",
        "metadata",
        "store",
        "prompt_cache_retention",
        "response_include",
        "top_logprobs",
        "context_management",
        "prompt_cache_options",
    )
    return {
        field_name: serialized[field_name]
        for field_name in supported_fields
        if serialized.get(field_name) is not None
    }


async def _request(
    client: _HttpClient,
    method: str,
    path: str,
    payload: Dict[str, Any],
) -> Any:
    if inspect.iscoroutinefunction(client.request):
        return await client.request(method, path, json=payload)
    return await asyncio.to_thread(client.request, method, path, payload)


async def _stream_lines(
    client: _HttpClient,
    method: str,
    path: str,
    payload: Dict[str, Any],
) -> AsyncIterator[str]:
    lines = client.stream_lines(method, path, json=payload)
    if hasattr(lines, "__aiter__"):
        async for line in lines:
            yield line
        return

    iterator = lines
    while True:
        has_value, line = await asyncio.to_thread(_next_line, iterator)
        if not has_value:
            return
        yield line


async def _stream_model_events(
    client: _HttpClient,
    path: str,
    payload: Dict[str, Any],
) -> AsyncIterator[TResponseStreamEvent]:
    event_name = "message"
    data_lines: List[str] = []
    async for line in _stream_lines(
        client,
        "POST",
        path,
        payload,
    ):
        if not line:
            if data_lines:
                event = _parse_sse_event(
                    event_name,
                    "\n".join(data_lines),
                )
                if event is not None:
                    yield event
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())

    if data_lines:
        event = _parse_sse_event(event_name, "\n".join(data_lines))
        if event is not None:
            yield event


def _next_line(iterator: Any) -> tuple[bool, str]:
    try:
        return True, next(iterator)
    except StopIteration:
        return False, ""


def _parse_sse_event(
    event_name: str,
    data: str,
) -> TResponseStreamEvent | None:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError("Relancify returned an invalid stream event") from exc
    if event_name == "billing":
        return None
    if event_name == "error":
        message = (
            payload.get("message")
            if isinstance(payload, dict)
            else "Text model stream failed"
        )
        raise RuntimeError(str(message))
    if event_name != "model.event" or not isinstance(payload, dict):
        raise ValueError(f"Unsupported Relancify stream event: {event_name}")
    return _STREAM_EVENT_ADAPTER.validate_python(payload)


def _parse_model_response(response: Any) -> ModelResponse:
    if not isinstance(response, dict) or not isinstance(
        response.get("response"),
        dict,
    ):
        raise ValueError("Relancify returned an invalid model response")
    payload = dict(response["response"])
    usage = payload.get("usage")
    if isinstance(usage, dict):
        usage = dict(usage)
        input_details = dict(usage.get("input_tokens_details") or {})
        input_details.setdefault("cache_write_tokens", 0)
        input_details.setdefault("cached_tokens", 0)
        output_details = dict(usage.get("output_tokens_details") or {})
        output_details.setdefault("reasoning_tokens", 0)
        usage["input_tokens_details"] = input_details
        usage["output_tokens_details"] = output_details
        usage.setdefault("request_usage_entries", [])
        payload["usage"] = usage
    return _MODEL_RESPONSE_ADAPTER.validate_python(payload)


def _to_json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_value(item) for item in value]
    return value
