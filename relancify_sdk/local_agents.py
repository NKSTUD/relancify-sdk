from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from agents import FunctionTool, Handoff
from agents.agent_output import AgentOutputSchemaBase
from agents.models.interface import Model, ModelResponse
from pydantic import BaseModel, TypeAdapter

from relancify_sdk.http import HttpClient


_MODEL_RESPONSE_ADAPTER = TypeAdapter(ModelResponse)


class RelancifyAgentModel(Model):
    """Agents SDK model adapter backed by Relancify-managed credentials."""

    def __init__(
        self,
        *,
        client: HttpClient,
        agent_id: str,
    ) -> None:
        self._client = client
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

        tool_choice = model_settings.tool_choice
        if tool_choice is not None and not isinstance(tool_choice, str):
            raise ValueError("Only function-tool choices are supported")

        payload = {
            "request_id": str(uuid4()),
            "input": _to_json_value(input),
            "system_instructions": system_instructions,
            "tools": [_serialize_function_tool(tool) for tool in tools],
            "output_schema": _serialize_output_schema(output_schema),
            "handoffs": [_serialize_handoff(handoff) for handoff in handoffs],
            "model_settings": _serialize_model_settings(model_settings),
            "tool_choice": tool_choice,
            "parallel_tool_calls": model_settings.parallel_tool_calls,
            "previous_response_id": previous_response_id,
            "conversation_id": conversation_id,
            "prompt": _serialize_prompt(prompt),
        }
        response = await asyncio.to_thread(
            self._client.request,
            "POST",
            f"/agents/{self._agent_id}/model/responses",
            payload,
        )
        if not isinstance(response, dict) or not isinstance(
            response.get("response"),
            dict,
        ):
            raise ValueError("Relancify returned an invalid model response")
        return _MODEL_RESPONSE_ADAPTER.validate_python(response["response"])

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
        del (
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id,
            conversation_id,
            prompt,
        )
        raise NotImplementedError("Local agent streaming is not supported yet")
        yield


def normalize_local_tools(tools: Optional[List[Any]]) -> List[FunctionTool]:
    normalized: List[FunctionTool] = []
    for tool in tools or []:
        if isinstance(tool, FunctionTool):
            normalized.append(tool)
            continue
        if callable(tool):
            from agents import function_tool

            normalized.append(function_tool(tool))
            continue
        raise TypeError(
            "Local tools must be Python callables or Agents SDK FunctionTool objects"
        )
    return normalized


def _serialize_function_tool(tool: Any) -> Dict[str, Any]:
    if not isinstance(tool, FunctionTool):
        raise TypeError("Only local Python function tools are supported")
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.params_json_schema,
        "strict": tool.strict_json_schema,
    }


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
    return {
        str(key): value
        for key, value in serialized.items()
        if value is not None
    }


def _serialize_model_settings(model_settings: Any) -> Dict[str, Any]:
    serialized = model_settings.to_json_dict()
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
    )
    return {
        field_name: serialized[field_name]
        for field_name in supported_fields
        if serialized.get(field_name) is not None
    }


def _to_json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_value(item) for item in value]
    return value
