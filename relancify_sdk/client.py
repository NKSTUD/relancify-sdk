from __future__ import annotations

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
from relancify_sdk.resources.api_keys import ApiKeysResource
from relancify_sdk.resources.billing import BillingResource
from relancify_sdk.resources.conversations import ConversationsResource
from relancify_sdk.resources.models import AsyncModelsResource, ModelsResource
from relancify_sdk.resources.operations import OperationsResource
from relancify_sdk.resources.runtime import RuntimeResource
from relancify_sdk.resources.tools import ToolsResource
from relancify_sdk.resources.users import UsersResource
from relancify_sdk.resources.voices import VoicesResource
from relancify_sdk.streaming import AsyncAgentStream, SyncAgentStream


class RelancifyClient:
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
        auth = AuthConfig(api_key=api_key, bearer=bearer)
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
        self.models = ModelsResource(self._http)
        self.operations = OperationsResource(self._http)
        self.runtime = RuntimeResource(self._http)
        self.tools = ToolsResource(self._http)
        self.users = UsersResource(self._http)
        self.voices = VoicesResource(self._http)

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
        """Run a native OpenAI Agents SDK loop through Relancify."""
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
        """Return a synchronous iterator over native Agents SDK stream events."""
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
        return SyncAgentStream(
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

    def __enter__(self) -> "RelancifyClient":
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
            raise TypeError("agent must be an Agents SDK Agent or a Relancify agent ID")

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


class AsyncRelancifyClient:
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
        auth = AuthConfig(api_key=api_key, bearer=bearer)
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
        self.models = AsyncModelsResource(self._http)

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
        """Asynchronously run a native OpenAI Agents SDK loop through Relancify."""
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
        """Return an async iterator over native Agents SDK stream events."""

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

        return AsyncAgentStream(start_stream)

    def clear_agent_cache(self, agent_id: Optional[str] = None) -> None:
        if agent_id is None:
            self._agent_cache.clear()
            return
        self._agent_cache.pop(_to_path_agent_id(agent_id), None)

    async def close(self) -> None:
        await self._http.close()

    async def aclose(self) -> None:
        await self.close()

    async def __aenter__(self) -> "AsyncRelancifyClient":
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
            raise TypeError("agent must be an Agents SDK Agent or a Relancify agent ID")

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
