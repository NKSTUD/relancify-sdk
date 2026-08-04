from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from agents import Agent, ModelSettings, RunConfig, Runner

from relancify_sdk.agent_runtime import (
    build_registered_agent,
    ensure_no_agent_definition_overrides,
    with_model_provider,
)
from relancify_sdk.auth import AuthConfig
from relancify_sdk.http import AsyncHttpClient, HttpClient
from relancify_sdk.local_agents import RelancifyModelProvider
from relancify_sdk.resources.agents import (
    AgentsResource,
    AsyncAgentsResource,
    _to_path_agent_id,
)
from relancify_sdk.resources.api_keys import ApiKeysResource, AsyncApiKeysResource
from relancify_sdk.resources.billing import AsyncBillingResource, BillingResource
from relancify_sdk.resources.conversations import (
    AsyncConversationsResource,
    ConversationsResource,
)
from relancify_sdk.resources.integrations import (
    AsyncIntegrationsResource,
    IntegrationsResource,
)
from relancify_sdk.resources.models import AsyncModelsResource, ModelsResource
from relancify_sdk.resources.operations import (
    AsyncOperationsResource,
    OperationsResource,
)
from relancify_sdk.resources.runtime import AsyncRuntimeResource, RuntimeResource
from relancify_sdk.resources.tools import AsyncToolsResource, ToolsResource
from relancify_sdk.resources.users import AsyncUsersResource, UsersResource
from relancify_sdk.resources.voices import AsyncVoicesResource, VoicesResource
from relancify_sdk.results import AgentRunResult
from relancify_sdk.streaming import AsyncAgentStream, SyncAgentStream


def _resolve_execution(agent: Agent | str, execution: Optional[str]) -> str:
    if not isinstance(agent, (Agent, str)):
        raise TypeError("agent must be an Agent or a Relancify agent ID")
    if execution is None:
        return "local" if isinstance(agent, Agent) else "hosted"
    normalized = str(execution).strip().lower()
    if normalized not in {"hosted", "local"}:
        raise ValueError("execution must be 'hosted' or 'local'")
    if isinstance(agent, Agent) and normalized == "hosted":
        raise ValueError(
            "A code-defined Agent only exists in the current process and cannot "
            "use hosted execution"
        )
    return normalized


def _ensure_hosted_arguments(
    *,
    input: Any,
    tools: Optional[List[Any]],
    output_type: Any,
    handoffs: Optional[List[Any]],
    input_guardrails: Optional[List[Any]],
    output_guardrails: Optional[List[Any]],
    agent_hooks: Any,
    model_settings: Optional[ModelSettings],
    prompt: Any,
    context: Any,
    max_turns: int,
    hooks: Any,
    run_config: RunConfig | Dict[str, Any] | None,
    error_handlers: Any,
    previous_response_id: Optional[str],
    auto_previous_response_id: bool,
    session: Any,
) -> str:
    if not isinstance(input, str):
        raise TypeError("Hosted execution requires input to be a string")
    local_only = {
        "tools": tools,
        "output_type": output_type,
        "handoffs": handoffs,
        "input_guardrails": input_guardrails,
        "output_guardrails": output_guardrails,
        "agent_hooks": agent_hooks,
        "model_settings": model_settings,
        "prompt": prompt,
        "context": context,
        "hooks": hooks,
        "run_config": run_config,
        "error_handlers": error_handlers,
        "previous_response_id": previous_response_id,
        "session": session,
    }
    provided = [name for name, value in local_only.items() if value is not None]
    if max_turns != 10:
        provided.append("max_turns")
    if auto_previous_response_id:
        provided.append("auto_previous_response_id")
    if provided:
        names = ", ".join(provided)
        raise TypeError(
            f"Hosted execution does not accept local runner arguments: {names}. "
            "Use execution='local' explicitly for a registered agent."
        )
    return input


class Relancify:
    def __init__(
        self,
        base_url: str = "https://api.relancify.com/api/v1",
        api_key: Optional[str] = None,
        bearer: Optional[str] = None,
        timeout: float = 30.0,
        agent_cache_ttl: float = 30.0,
    ) -> None:
        if agent_cache_ttl < 0:
            raise ValueError("agent_cache_ttl must be zero or greater")
        auth = AuthConfig(
            api_key=api_key or os.environ.get("RELANCIFY_API_KEY"),
            bearer=bearer,
        )
        self._http = HttpClient(base_url=base_url, auth=auth, timeout=timeout)
        self._model_provider = RelancifyModelProvider(self._http)
        self._agent_cache_ttl = float(agent_cache_ttl)
        self._agent_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}

        self.agents = AgentsResource(
            self._http,
            on_change=self.clear_agent_cache,
        )
        self.api_keys = ApiKeysResource(self._http)
        self.billing = BillingResource(self._http)
        self.conversations = ConversationsResource(self._http)
        self.integrations = IntegrationsResource(self._http)
        self.models = ModelsResource(self._http)
        self.operations = OperationsResource(self._http)
        self.runtime = RuntimeResource(self._http)
        self.tools = ToolsResource(self._http)
        self.users = UsersResource(self._http)
        self.voices = VoicesResource(self._http)

    def run(
        self,
        agent: Agent | str,
        input: Any,
        *,
        execution: Optional[str] = None,
        request_id: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        agent_hooks: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
        context: Any = None,
        max_turns: int = 10,
        hooks: Any = None,
        run_config: RunConfig | Dict[str, Any] | None = None,
        error_handlers: Any = None,
        previous_response_id: Optional[str] = None,
        auto_previous_response_id: bool = False,
        conversation_id: Optional[str] = None,
        session: Any = None,
    ) -> AgentRunResult:
        """Run a code-defined or registered agent through one stable API."""
        resolved_execution = _resolve_execution(agent, execution)
        if resolved_execution == "hosted":
            hosted_input = _ensure_hosted_arguments(
                input=input,
                tools=tools,
                output_type=output_type,
                handoffs=handoffs,
                input_guardrails=input_guardrails,
                output_guardrails=output_guardrails,
                agent_hooks=agent_hooks,
                model_settings=model_settings,
                prompt=prompt,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                session=session,
            )
            response = self.agents.run_text(
                str(agent),
                input=hosted_input,
                conversation_id=conversation_id,
                request_id=request_id,
            )
            return AgentRunResult.from_hosted(response)

        if request_id is not None:
            raise TypeError("request_id is only supported by hosted execution")

        native_result = self.invoke(
            agent,
            input,
            tools=tools,
            output_type=output_type,
            handoffs=handoffs,
            input_guardrails=input_guardrails,
            output_guardrails=output_guardrails,
            agent_hooks=agent_hooks,
            model_settings=model_settings,
            prompt=prompt,
            context=context,
            max_turns=max_turns,
            hooks=hooks,
            run_config=run_config,
            error_handlers=error_handlers,
            previous_response_id=previous_response_id,
            auto_previous_response_id=auto_previous_response_id,
            conversation_id=conversation_id,
            session=session,
        )
        return AgentRunResult.from_local(native_result)

    def invoke(
        self,
        agent: Agent | str,
        input: Any,
        *,
        tools: Optional[List[Any]] = None,
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        agent_hooks: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
        context: Any = None,
        max_turns: int = 10,
        hooks: Any = None,
        run_config: RunConfig | Dict[str, Any] | None = None,
        error_handlers: Any = None,
        previous_response_id: Optional[str] = None,
        auto_previous_response_id: bool = False,
        conversation_id: Optional[str] = None,
        session: Any = None,
    ) -> Any:
        """Run a local agent orchestration loop through Relancify."""
        starting_agent = self._resolve_agent(
            agent,
            tools=tools,
            output_type=output_type,
            handoffs=handoffs,
            input_guardrails=input_guardrails,
            output_guardrails=output_guardrails,
            agent_hooks=agent_hooks,
            model_settings=model_settings,
            prompt=prompt,
        )
        return Runner.run_sync(
            starting_agent,
            input,
            context=context,
            max_turns=max(1, int(max_turns)),
            hooks=hooks,
            run_config=with_model_provider(
                run_config,
                model_provider=self._model_provider,
            ),
            error_handlers=error_handlers,
            previous_response_id=previous_response_id,
            auto_previous_response_id=auto_previous_response_id,
            conversation_id=conversation_id,
            session=session,
        )

    def stream(
        self,
        agent: Agent | str,
        input: Any,
        *,
        execution: Optional[str] = None,
        request_id: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        agent_hooks: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
        context: Any = None,
        max_turns: int = 10,
        hooks: Any = None,
        run_config: RunConfig | Dict[str, Any] | None = None,
        error_handlers: Any = None,
        previous_response_id: Optional[str] = None,
        auto_previous_response_id: bool = False,
        conversation_id: Optional[str] = None,
        session: Any = None,
    ) -> SyncAgentStream:
        """Stream normalized hosted or local agent events."""
        resolved_execution = _resolve_execution(agent, execution)
        if resolved_execution == "hosted":
            hosted_input = _ensure_hosted_arguments(
                input=input,
                tools=tools,
                output_type=output_type,
                handoffs=handoffs,
                input_guardrails=input_guardrails,
                output_guardrails=output_guardrails,
                agent_hooks=agent_hooks,
                model_settings=model_settings,
                prompt=prompt,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                session=session,
            )
            return SyncAgentStream.hosted(
                self.agents.stream_run(
                    str(agent),
                    input=hosted_input,
                    conversation_id=conversation_id,
                    request_id=request_id,
                )
            )

        if request_id is not None:
            raise TypeError("request_id is only supported by hosted execution")

        starting_agent = self._resolve_agent(
            agent,
            tools=tools,
            output_type=output_type,
            handoffs=handoffs,
            input_guardrails=input_guardrails,
            output_guardrails=output_guardrails,
            agent_hooks=agent_hooks,
            model_settings=model_settings,
            prompt=prompt,
        )
        effective_run_config = with_model_provider(
            run_config,
            model_provider=self._model_provider,
        )
        return SyncAgentStream.local(
            lambda: Runner.run_streamed(
                starting_agent,
                input,
                context=context,
                max_turns=max(1, int(max_turns)),
                hooks=hooks,
                run_config=effective_run_config,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                conversation_id=conversation_id,
                session=session,
                error_handlers=error_handlers,
            )
        )

    def clear_agent_cache(self, agent_id: Optional[str] = None) -> None:
        if agent_id is None:
            self._agent_cache.clear()
            return
        self._agent_cache.pop(_to_path_agent_id(agent_id), None)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Relancify":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def _resolve_agent(
        self,
        agent: Agent | str,
        *,
        tools: Optional[List[Any]],
        output_type: Any,
        handoffs: Optional[List[Any]],
        input_guardrails: Optional[List[Any]],
        output_guardrails: Optional[List[Any]],
        agent_hooks: Any,
        model_settings: Optional[ModelSettings],
        prompt: Any,
    ) -> Agent:
        if isinstance(agent, Agent):
            ensure_no_agent_definition_overrides(
                agent,
                tools=tools,
                output_type=output_type,
                handoffs=handoffs,
                input_guardrails=input_guardrails,
                output_guardrails=output_guardrails,
                agent_hooks=agent_hooks,
                model_settings=model_settings,
                prompt=prompt,
            )
            return agent
        if not isinstance(agent, str):
            raise TypeError("agent must be an Agent or a Relancify agent ID")

        agent_id = _to_path_agent_id(agent)
        return build_registered_agent(
            config=self._get_registered_agent(agent_id),
            client=self._http,
            agent_id=agent_id,
            tools=tools,
            output_type=output_type,
            handoffs=handoffs,
            input_guardrails=input_guardrails,
            output_guardrails=output_guardrails,
            hooks=agent_hooks,
            model_settings=model_settings,
            prompt=prompt,
        )

    def _get_registered_agent(self, agent_id: str) -> Dict[str, Any]:
        now = time.monotonic()
        cached = self._agent_cache.get(agent_id)
        if cached is not None and cached[0] > now:
            return cached[1]

        config = self.agents.get(agent_id)
        if not isinstance(config, dict):
            raise ValueError("Relancify returned an invalid registered agent")
        self._agent_cache[agent_id] = (
            now + self._agent_cache_ttl,
            config,
        )
        return config


class AsyncRelancify:
    def __init__(
        self,
        base_url: str = "https://api.relancify.com/api/v1",
        api_key: Optional[str] = None,
        bearer: Optional[str] = None,
        timeout: float = 30.0,
        agent_cache_ttl: float = 30.0,
    ) -> None:
        if agent_cache_ttl < 0:
            raise ValueError("agent_cache_ttl must be zero or greater")
        auth = AuthConfig(
            api_key=api_key or os.environ.get("RELANCIFY_API_KEY"),
            bearer=bearer,
        )
        self._http = AsyncHttpClient(
            base_url=base_url,
            auth=auth,
            timeout=timeout,
        )
        self._model_provider = RelancifyModelProvider(self._http)
        self._agent_cache_ttl = float(agent_cache_ttl)
        self._agent_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self.agents = AsyncAgentsResource(
            self._http,
            on_change=self.clear_agent_cache,
        )
        self.api_keys = AsyncApiKeysResource(self._http)
        self.billing = AsyncBillingResource(self._http)
        self.conversations = AsyncConversationsResource(self._http)
        self.models = AsyncModelsResource(self._http)
        self.integrations = AsyncIntegrationsResource(self._http)
        self.operations = AsyncOperationsResource(self._http)
        self.runtime = AsyncRuntimeResource(self._http)
        self.tools = AsyncToolsResource(self._http)
        self.users = AsyncUsersResource(self._http)
        self.voices = AsyncVoicesResource(self._http)

    async def run(
        self,
        agent: Agent | str,
        input: Any,
        *,
        execution: Optional[str] = None,
        request_id: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        agent_hooks: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
        context: Any = None,
        max_turns: int = 10,
        hooks: Any = None,
        run_config: RunConfig | Dict[str, Any] | None = None,
        error_handlers: Any = None,
        previous_response_id: Optional[str] = None,
        auto_previous_response_id: bool = False,
        conversation_id: Optional[str] = None,
        session: Any = None,
    ) -> AgentRunResult:
        """Asynchronously run a code-defined or registered agent."""
        resolved_execution = _resolve_execution(agent, execution)
        if resolved_execution == "hosted":
            hosted_input = _ensure_hosted_arguments(
                input=input,
                tools=tools,
                output_type=output_type,
                handoffs=handoffs,
                input_guardrails=input_guardrails,
                output_guardrails=output_guardrails,
                agent_hooks=agent_hooks,
                model_settings=model_settings,
                prompt=prompt,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                session=session,
            )
            response = await self.agents.run_text(
                str(agent),
                input=hosted_input,
                conversation_id=conversation_id,
                request_id=request_id,
            )
            return AgentRunResult.from_hosted(response)

        if request_id is not None:
            raise TypeError("request_id is only supported by hosted execution")

        native_result = await self.invoke(
            agent,
            input,
            tools=tools,
            output_type=output_type,
            handoffs=handoffs,
            input_guardrails=input_guardrails,
            output_guardrails=output_guardrails,
            agent_hooks=agent_hooks,
            model_settings=model_settings,
            prompt=prompt,
            context=context,
            max_turns=max_turns,
            hooks=hooks,
            run_config=run_config,
            error_handlers=error_handlers,
            previous_response_id=previous_response_id,
            auto_previous_response_id=auto_previous_response_id,
            conversation_id=conversation_id,
            session=session,
        )
        return AgentRunResult.from_local(native_result)

    async def invoke(
        self,
        agent: Agent | str,
        input: Any,
        *,
        tools: Optional[List[Any]] = None,
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        agent_hooks: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
        context: Any = None,
        max_turns: int = 10,
        hooks: Any = None,
        run_config: RunConfig | Dict[str, Any] | None = None,
        error_handlers: Any = None,
        previous_response_id: Optional[str] = None,
        auto_previous_response_id: bool = False,
        conversation_id: Optional[str] = None,
        session: Any = None,
    ) -> Any:
        """Asynchronously run a local agent orchestration loop through Relancify."""
        starting_agent = await self._resolve_agent(
            agent,
            tools=tools,
            output_type=output_type,
            handoffs=handoffs,
            input_guardrails=input_guardrails,
            output_guardrails=output_guardrails,
            agent_hooks=agent_hooks,
            model_settings=model_settings,
            prompt=prompt,
        )
        return await Runner.run(
            starting_agent,
            input,
            context=context,
            max_turns=max(1, int(max_turns)),
            hooks=hooks,
            run_config=with_model_provider(
                run_config,
                model_provider=self._model_provider,
            ),
            error_handlers=error_handlers,
            previous_response_id=previous_response_id,
            auto_previous_response_id=auto_previous_response_id,
            conversation_id=conversation_id,
            session=session,
        )

    def stream(
        self,
        agent: Agent | str,
        input: Any,
        *,
        execution: Optional[str] = None,
        request_id: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        output_type: Any = None,
        handoffs: Optional[List[Any]] = None,
        input_guardrails: Optional[List[Any]] = None,
        output_guardrails: Optional[List[Any]] = None,
        agent_hooks: Any = None,
        model_settings: Optional[ModelSettings] = None,
        prompt: Any = None,
        context: Any = None,
        max_turns: int = 10,
        hooks: Any = None,
        run_config: RunConfig | Dict[str, Any] | None = None,
        error_handlers: Any = None,
        previous_response_id: Optional[str] = None,
        auto_previous_response_id: bool = False,
        conversation_id: Optional[str] = None,
        session: Any = None,
    ) -> AsyncAgentStream:
        """Stream normalized hosted or local agent events."""

        resolved_execution = _resolve_execution(agent, execution)
        if resolved_execution == "hosted":
            hosted_input = _ensure_hosted_arguments(
                input=input,
                tools=tools,
                output_type=output_type,
                handoffs=handoffs,
                input_guardrails=input_guardrails,
                output_guardrails=output_guardrails,
                agent_hooks=agent_hooks,
                model_settings=model_settings,
                prompt=prompt,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                session=session,
            )
            return AsyncAgentStream.hosted(
                self.agents.stream_run(
                    str(agent),
                    input=hosted_input,
                    conversation_id=conversation_id,
                    request_id=request_id,
                )
            )

        if request_id is not None:
            raise TypeError("request_id is only supported by hosted execution")

        async def start_stream() -> Any:
            starting_agent = await self._resolve_agent(
                agent,
                tools=tools,
                output_type=output_type,
                handoffs=handoffs,
                input_guardrails=input_guardrails,
                output_guardrails=output_guardrails,
                agent_hooks=agent_hooks,
                model_settings=model_settings,
                prompt=prompt,
            )
            return Runner.run_streamed(
                starting_agent,
                input,
                context=context,
                max_turns=max(1, int(max_turns)),
                hooks=hooks,
                run_config=with_model_provider(
                    run_config,
                    model_provider=self._model_provider,
                ),
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                conversation_id=conversation_id,
                session=session,
                error_handlers=error_handlers,
            )

        return AsyncAgentStream.local(start_stream)

    def clear_agent_cache(self, agent_id: Optional[str] = None) -> None:
        if agent_id is None:
            self._agent_cache.clear()
            return
        self._agent_cache.pop(_to_path_agent_id(agent_id), None)

    async def close(self) -> None:
        await self._http.close()

    async def aclose(self) -> None:
        await self.close()

    async def __aenter__(self) -> "AsyncRelancify":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.close()

    async def _resolve_agent(
        self,
        agent: Agent | str,
        *,
        tools: Optional[List[Any]],
        output_type: Any,
        handoffs: Optional[List[Any]],
        input_guardrails: Optional[List[Any]],
        output_guardrails: Optional[List[Any]],
        agent_hooks: Any,
        model_settings: Optional[ModelSettings],
        prompt: Any,
    ) -> Agent:
        if isinstance(agent, Agent):
            ensure_no_agent_definition_overrides(
                agent,
                tools=tools,
                output_type=output_type,
                handoffs=handoffs,
                input_guardrails=input_guardrails,
                output_guardrails=output_guardrails,
                agent_hooks=agent_hooks,
                model_settings=model_settings,
                prompt=prompt,
            )
            return agent
        if not isinstance(agent, str):
            raise TypeError("agent must be an Agent or a Relancify agent ID")

        agent_id = _to_path_agent_id(agent)
        return build_registered_agent(
            config=await self._get_registered_agent(agent_id),
            client=self._http,
            agent_id=agent_id,
            tools=tools,
            output_type=output_type,
            handoffs=handoffs,
            input_guardrails=input_guardrails,
            output_guardrails=output_guardrails,
            hooks=agent_hooks,
            model_settings=model_settings,
            prompt=prompt,
        )

    async def _get_registered_agent(self, agent_id: str) -> Dict[str, Any]:
        now = time.monotonic()
        cached = self._agent_cache.get(agent_id)
        if cached is not None and cached[0] > now:
            return cached[1]

        config = await self.agents.get(agent_id)
        if not isinstance(config, dict):
            raise ValueError("Relancify returned an invalid registered agent")
        self._agent_cache[agent_id] = (
            now + self._agent_cache_ttl,
            config,
        )
        return config
