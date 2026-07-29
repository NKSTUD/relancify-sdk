from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional

from agents import Agent, ModelSettings, RunConfig

from relancify_sdk.http import AsyncHttpClient, HttpClient
from relancify_sdk.local_agents import RelancifyAgentModel, normalize_local_tools


def build_registered_agent(
    *,
    config: Dict[str, Any],
    client: HttpClient | AsyncHttpClient,
    agent_id: str,
    tools: Optional[List[Any]] = None,
    output_type: Any = None,
    handoffs: Optional[List[Any]] = None,
    input_guardrails: Optional[List[Any]] = None,
    output_guardrails: Optional[List[Any]] = None,
    hooks: Any = None,
    model_settings: Optional[ModelSettings] = None,
    prompt: Any = None,
) -> Agent:
    if config.get("modality") != "text":
        raise ValueError("Only registered text agents can be invoked with this client")

    prompt_config = config.get("prompt")
    llm = config.get("llm")
    if not isinstance(prompt_config, dict):
        raise ValueError("Registered agent prompt configuration is invalid")
    if not isinstance(llm, dict):
        raise ValueError("Registered agent model configuration is invalid")

    instructions = str(prompt_config.get("system") or "").strip()
    model_name = str(llm.get("model") or "").strip()
    if not instructions:
        raise ValueError("Registered agent prompt.system is required")
    if not model_name:
        raise ValueError("Registered agent llm.model is required")

    configured_settings = _build_model_settings(llm)
    return Agent(
        name=str(config.get("name") or "Relancify agent"),
        instructions=instructions,
        prompt=prompt,
        handoffs=list(handoffs or []),
        model=RelancifyAgentModel(
            client=client,
            agent_id=agent_id,
            model_name=model_name,
        ),
        model_settings=configured_settings.resolve(model_settings),
        tools=normalize_local_tools(tools),
        input_guardrails=list(input_guardrails or []),
        output_guardrails=list(output_guardrails or []),
        output_type=output_type,
        hooks=hooks,
    )


def with_model_provider(
    run_config: RunConfig | Dict[str, Any] | None,
    *,
    model_provider: Any,
) -> RunConfig | Dict[str, Any]:
    if run_config is None:
        return RunConfig(model_provider=model_provider)
    if isinstance(run_config, dict):
        return {**run_config, "model_provider": model_provider}
    return replace(run_config, model_provider=model_provider)


def ensure_no_agent_definition_overrides(
    agent: Agent,
    *,
    tools: Optional[List[Any]],
    output_type: Any,
    handoffs: Optional[List[Any]],
    input_guardrails: Optional[List[Any]],
    output_guardrails: Optional[List[Any]],
    agent_hooks: Any,
    model_settings: Optional[ModelSettings],
    prompt: Any,
) -> None:
    del agent
    provided_names = [
        name
        for name, value in (
            ("tools", tools),
            ("output_type", output_type),
            ("handoffs", handoffs),
            ("input_guardrails", input_guardrails),
            ("output_guardrails", output_guardrails),
            ("agent_hooks", agent_hooks),
            ("model_settings", model_settings),
            ("prompt", prompt),
        )
        if value is not None
    ]
    if provided_names:
        names = ", ".join(provided_names)
        raise TypeError(
            f"{names} can only be supplied when invoking a registered agent ID. "
            "For a code-defined Agent, configure these fields on Agent(...)."
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
