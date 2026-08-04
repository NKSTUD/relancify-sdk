import asyncio
import json as json_module
import time

from agents import (
    Agent,
    CustomTool,
    FunctionTool,
    GuardrailFunctionOutput,
    ModelSettings,
    ProgrammaticToolCallingTool,
    RunConfig,
    RunHooks,
    SQLiteSession,
    ToolSearchTool,
    input_guardrail,
)
from agents.items import TResponseStreamEvent
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseOutputMessage,
    ResponseOutputText,
)
from pydantic import BaseModel, TypeAdapter

from relancify_sdk.agent_runtime import with_model_provider
from relancify_sdk.client import AsyncRelancify, Relancify
from relancify_sdk.local_agents import RelancifyModelProvider
from relancify_sdk.resources.agents import AgentsResource, AsyncAgentsResource
from relancify_sdk.resources.models import ModelsResource

AGENT_ID = "ag_12345678-1234-1234-1234-123456789abc"


def test_relancify_run_config_always_disables_openai_tracing() -> None:
    provider = object()

    default_config = with_model_provider(None, model_provider=provider)
    dictionary_config = with_model_provider(
        {"tracing_disabled": False},
        model_provider=provider,
    )
    explicit_config = with_model_provider(
        RunConfig(tracing_disabled=False),
        model_provider=provider,
    )

    assert default_config.model_provider is provider
    assert default_config.tracing_disabled is True
    assert dictionary_config["model_provider"] is provider
    assert dictionary_config["tracing_disabled"] is True
    assert explicit_config.model_provider is provider
    assert explicit_config.tracing_disabled is True


def _model_response(text: str = "Hello from Relancify.") -> dict:
    return {
        "response": {
            "output": [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": text,
                            "annotations": [],
                            "logprobs": [],
                        }
                    ],
                }
            ],
            "usage": {
                "requests": 1,
                "input_tokens": 2,
                "input_tokens_details": {
                    "cache_write_tokens": 0,
                    "cached_tokens": 0,
                },
                "output_tokens": 3,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 5,
                "request_usage_entries": [],
            },
            "response_id": "resp_1",
            "request_id": None,
        },
        "billing": {"credits_debited": 1},
    }


def _function_call_response(name: str) -> dict:
    response = _model_response()
    response["response"]["output"] = [
        {
            "type": "function_call",
            "id": "fc_handoff",
            "call_id": "call_handoff",
            "name": name,
            "arguments": "{}",
            "status": "completed",
        }
    ]
    return response


class CodeFirstHttpClient:
    def __init__(self, response_text: str = "Hello from Relancify.") -> None:
        self.calls = []
        self.get_count = 0
        self.response_text = response_text

    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        if method == "GET":
            self.get_count += 1
            return {
                "id": AGENT_ID,
                "name": "Registered support",
                "modality": "text",
                "prompt": {"system": "Answer registered support questions."},
                "llm": {"model": "support-fast", "temperature": 0.2},
            }
        return _model_response(self.response_text)

    def close(self) -> None:
        return None


class AsyncCodeFirstHttpClient:
    def __init__(self) -> None:
        self.calls = []
        self.get_count = 0

    async def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        if method == "GET":
            self.get_count += 1
            return {
                "id": AGENT_ID,
                "name": "Registered support",
                "modality": "text",
                "prompt": {"system": "Answer registered support questions."},
                "llm": {"model": "support-fast", "temperature": 0.2},
            }
        return _model_response("Async response.")

    async def close(self) -> None:
        return None

    async def stream_lines(self, method, path, json=None):
        self.calls.append((method, path, json))
        for event in _model_stream_events():
            yield "event: model.event"
            yield "data: " + json_module.dumps(event)
            yield ""


class StreamingCodeFirstHttpClient(CodeFirstHttpClient):
    def stream_lines(self, method, path, json=None):
        self.calls.append((method, path, json))
        for event in _model_stream_events():
            yield "event: model.event"
            yield "data: " + json_module.dumps(event)
            yield ""


class CodeFirstHandoffHttpClient(CodeFirstHttpClient):
    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        if json["model"] == "support-fast":
            return _function_call_response("transfer_to_billing")
        return _model_response('{"status":"resolved","message":"Invoice corrected."}')


def _model_stream_events() -> list[dict]:
    response_fields = {
        "id": "resp_stream",
        "created_at": 0.0,
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "metadata": {},
        "model": "support-fast",
        "object": "response",
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }
    created_response = Response(
        **response_fields,
        output=[],
        status="in_progress",
        usage=None,
    )
    output_message = ResponseOutputMessage(
        id="msg_stream",
        content=[
            ResponseOutputText(
                annotations=[],
                text="Streamed response.",
                type="output_text",
                logprobs=[],
            )
        ],
        role="assistant",
        status="completed",
        type="message",
    )
    completed_response = Response(
        **response_fields,
        output=[output_message],
        status="completed",
        usage={
            "input_tokens": 2,
            "input_tokens_details": {
                "cache_write_tokens": 0,
                "cached_tokens": 0,
            },
            "output_tokens": 3,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 5,
        },
    )
    adapter = TypeAdapter(TResponseStreamEvent)
    return [
        adapter.dump_python(
            ResponseCreatedEvent(
                response=created_response,
                sequence_number=0,
                type="response.created",
            ),
            mode="json",
        ),
        adapter.dump_python(
            ResponseCompletedEvent(
                response=completed_response,
                sequence_number=1,
                type="response.completed",
            ),
            mode="json",
        ),
    ]


def _sync_client(http: CodeFirstHttpClient) -> Relancify:
    client = object.__new__(Relancify)
    client._http = http
    client._model_provider = RelancifyModelProvider(http)
    client._agent_cache_ttl = 30.0
    client._agent_cache = {}
    client.agents = AgentsResource(
        http,
        on_change=client.clear_agent_cache,
    )
    return client


def _async_client(http: AsyncCodeFirstHttpClient) -> AsyncRelancify:
    client = object.__new__(AsyncRelancify)
    client._http = http
    client._model_provider = RelancifyModelProvider(http)
    client._agent_cache_ttl = 30.0
    client._agent_cache = {}
    client.agents = AsyncAgentsResource(
        http,
        on_change=client.clear_agent_cache,
    )
    return client


def test_code_defined_agent_uses_simple_model_name_and_v019_settings() -> None:
    http = CodeFirstHttpClient()
    client = _sync_client(http)

    async def execute_tool(_context, _arguments):
        return {"status": "ok"}

    tool = FunctionTool(
        name="find_order",
        description="Find an order.",
        params_json_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
        on_invoke_tool=execute_tool,
        defer_loading=True,
        allowed_callers=["programmatic"],
        output_json_schema={
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
            "additionalProperties": False,
        },
    )
    custom_tool = CustomTool(
        name="query_orders",
        description="Query orders with a text expression.",
        on_invoke_tool=execute_tool,
        format={"type": "text"},
        defer_loading=True,
        allowed_callers=["programmatic"],
    )
    agent = Agent(
        name="Support",
        instructions="Answer clearly.",
        model="support-fast",
        tools=[
            tool,
            custom_tool,
            ToolSearchTool(execution="server"),
            ProgrammaticToolCallingTool(),
        ],
        model_settings=ModelSettings(
            context_management=[{"type": "compaction", "compact_threshold": 10_000}],
            prompt_cache_options={"mode": "explicit", "ttl": "30m"},
        ),
    )

    result = client.invoke(
        agent,
        input="Hello",
        run_config=RunConfig(tracing_disabled=True),
    )

    assert result.final_output == "Hello from Relancify."
    method, path, payload = http.calls[0]
    assert (method, path) == ("POST", "/models/responses")
    assert payload["model"] == "support-fast"
    assert payload["tools"][0]["output_schema"]["required"] == ["status"]
    assert payload["tools"][0]["allowed_callers"] == ["programmatic"]
    assert payload["tools"][0]["defer_loading"] is True
    assert payload["tools"][1]["type"] == "custom"
    assert payload["tools"][1]["format"] == {"type": "text"}
    assert payload["tools"][2] == {
        "type": "tool_search",
        "execution": "server",
    }
    assert payload["tools"][3] == {"type": "programmatic_tool_calling"}
    assert payload["model_settings"]["context_management"][0]["type"] == ("compaction")
    assert payload["model_settings"]["prompt_cache_options"] == {
        "mode": "explicit",
        "ttl": "30m",
    }


def test_registered_agent_id_is_loaded_once_within_cache_ttl() -> None:
    http = CodeFirstHttpClient()
    client = _sync_client(http)

    first = client.invoke(
        AGENT_ID,
        input="First",
        run_config=RunConfig(tracing_disabled=True),
    )
    second = client.invoke(
        AGENT_ID,
        input="Second",
        run_config=RunConfig(tracing_disabled=True),
    )

    assert first.final_output == second.final_output == "Hello from Relancify."
    assert http.get_count == 1
    model_paths = [path for method, path, _payload in http.calls if method == "POST"]
    assert model_paths == [
        f"/agents/{AGENT_ID}/model/responses",
        f"/agents/{AGENT_ID}/model/responses",
    ]


def test_code_defined_agent_keeps_native_structured_output() -> None:
    class SupportAnswer(BaseModel):
        answer: str
        requires_human: bool

    http = CodeFirstHttpClient(
        '{"answer":"Your order is ready.","requires_human":false}'
    )
    client = _sync_client(http)
    agent = Agent(
        name="Structured support",
        instructions="Return a structured support answer.",
        model="support-fast",
        output_type=SupportAnswer,
    )

    result = client.invoke(
        agent,
        input="Where is my order?",
        run_config=RunConfig(tracing_disabled=True),
    )

    assert result.final_output == SupportAnswer(
        answer="Your order is ready.",
        requires_human=False,
    )
    assert http.calls[0][2]["output_schema"]["name"] == "SupportAnswer"


def test_code_defined_agents_keep_native_handoffs() -> None:
    class BillingResolution(BaseModel):
        status: str
        message: str

    http = CodeFirstHandoffHttpClient()
    client = _sync_client(http)
    billing_agent = Agent(
        name="Billing",
        instructions="Resolve billing requests.",
        model="support-precise",
        output_type=BillingResolution,
    )
    triage_agent = Agent(
        name="Triage",
        instructions="Transfer billing requests.",
        model="support-fast",
        handoffs=[billing_agent],
    )

    result = client.invoke(
        triage_agent,
        input="My invoice is incorrect.",
        run_config=RunConfig(tracing_disabled=True),
    )

    assert result.last_agent.name == "Billing"
    assert result.final_output == BillingResolution(
        status="resolved",
        message="Invoice corrected.",
    )
    assert http.calls[0][2]["handoffs"][0]["tool_name"] == ("transfer_to_billing")
    assert http.calls[1][2]["model"] == "support-precise"


def test_invoke_preserves_context_hooks_guardrails_and_sessions() -> None:
    guardrail_contexts = []

    @input_guardrail(run_in_parallel=False)
    def allow_input(context, _agent, input):
        guardrail_contexts.append((context.context, input))
        return GuardrailFunctionOutput(
            output_info={"allowed": True},
            tripwire_triggered=False,
        )

    class RecordingHooks(RunHooks):
        def __init__(self) -> None:
            self.contexts = []

        async def on_agent_start(self, context, _agent) -> None:
            self.contexts.append(context.context)

    http = CodeFirstHttpClient()
    client = _sync_client(http)
    hooks = RecordingHooks()
    session = SQLiteSession("support-session")
    agent = Agent(
        name="Stateful support",
        instructions="Remember the conversation.",
        model="support-fast",
        input_guardrails=[allow_input],
    )
    run_context = {"tenant_id": "tenant_123"}

    try:
        client.invoke(
            agent,
            input="First question",
            context=run_context,
            hooks=hooks,
            session=session,
            run_config=RunConfig(tracing_disabled=True),
        )
        client.invoke(
            agent,
            input="Follow-up question",
            context=run_context,
            hooks=hooks,
            session=session,
            run_config=RunConfig(tracing_disabled=True),
        )
    finally:
        session.close()

    assert hooks.contexts == [run_context, run_context]
    assert [item[0] for item in guardrail_contexts] == [
        run_context,
        run_context,
    ]
    second_input = http.calls[1][2]["input"]
    assert any(
        item.get("role") == "assistant"
        and item["content"][0]["text"] == "Hello from Relancify."
        for item in second_input
    )
    assert any(
        item.get("role") == "user" and item["content"] == "Follow-up question"
        for item in second_input
    )


def test_expired_registered_agent_cache_is_refreshed() -> None:
    http = CodeFirstHttpClient()
    client = _sync_client(http)
    client._agent_cache[AGENT_ID] = (
        time.monotonic() - 1,
        {"modality": "text"},
    )

    client.invoke(
        AGENT_ID,
        input="Refresh",
        run_config=RunConfig(tracing_disabled=True),
    )

    assert http.get_count == 1


def test_sdk_agent_update_invalidates_registered_agent_cache() -> None:
    http = CodeFirstHttpClient()
    client = _sync_client(http)

    client.invoke(
        AGENT_ID,
        input="Before update",
        run_config=RunConfig(tracing_disabled=True),
    )
    client.agents.update(
        AGENT_ID,
        {"prompt": {"system": "Updated instructions."}},
    )
    client.invoke(
        AGENT_ID,
        input="After update",
        run_config=RunConfig(tracing_disabled=True),
    )

    assert http.get_count == 2


def test_async_client_invokes_code_defined_agent() -> None:
    async def run() -> None:
        http = AsyncCodeFirstHttpClient()
        client = _async_client(http)
        agent = Agent(
            name="Async support",
            instructions="Answer clearly.",
            model="support-fast",
        )

        result = await client.invoke(
            agent,
            input="Hello",
            run_config=RunConfig(tracing_disabled=True),
        )

        assert result.final_output == "Async response."
        assert http.calls[0][1] == "/models/responses"

    asyncio.run(run())


def test_async_client_invokes_registered_agent_id() -> None:
    async def run() -> None:
        http = AsyncCodeFirstHttpClient()
        client = _async_client(http)

        result = await client.invoke(
            AGENT_ID,
            input="Hello",
            run_config=RunConfig(tracing_disabled=True),
        )

        assert result.final_output == "Async response."
        assert http.get_count == 1
        assert http.calls[0][1] == f"/agents/{AGENT_ID}"
        assert http.calls[1][1] == f"/agents/{AGENT_ID}/model/responses"

    asyncio.run(run())


def test_provider_specific_model_overrides_fail_clearly() -> None:
    http = CodeFirstHttpClient()
    client = _sync_client(http)
    agent = Agent(
        name="Unsafe override",
        instructions="Answer.",
        model="support-fast",
        model_settings=ModelSettings(extra_body={"provider_secret": True}),
    )

    try:
        client.invoke(
            agent,
            input="Hello",
            run_config=RunConfig(tracing_disabled=True),
        )
    except ValueError as exc:
        assert "extra_body" in str(exc)
        assert "managed routing" in str(exc)
    else:
        raise AssertionError("Expected provider-specific override rejection")


def test_public_model_catalog_is_available_without_provider_names() -> None:
    http = CodeFirstHttpClient()
    models = ModelsResource(http)

    models.list(page=2, page_size=25)

    assert http.calls[0][:2] == (
        "GET",
        "/models?page=2&page_size=25",
    )


def test_sync_stream_exposes_normalized_events_and_raw_native_details() -> None:
    http = StreamingCodeFirstHttpClient()
    client = _sync_client(http)
    agent = Agent(
        name="Streaming support",
        instructions="Answer clearly.",
        model="support-fast",
    )

    stream = client.stream(
        agent,
        input="Hello",
        run_config=RunConfig(tracing_disabled=True),
    )
    events = list(stream)

    assert events
    assert events[0].type == "run.started"
    assert events[-1].type == "run.completed"
    assert any(event.raw is not None for event in events)
    assert stream.result.execution == "local"
    assert stream.final_output == "Streamed response."
    assert http.calls[0][1] == "/models/responses/stream"


def test_registered_agent_stream_uses_agent_billing_route() -> None:
    http = StreamingCodeFirstHttpClient()
    client = _sync_client(http)

    stream = client.stream(
        AGENT_ID,
        input="Hello",
        execution="local",
        run_config=RunConfig(tracing_disabled=True),
    )
    events = list(stream)

    assert events
    assert stream.final_output == "Streamed response."
    assert http.calls[0][1] == f"/agents/{AGENT_ID}"
    assert http.calls[1][1] == (f"/agents/{AGENT_ID}/model/responses/stream")
    assert "model" not in http.calls[1][2]


def test_async_stream_exposes_normalized_runner_events() -> None:
    async def run() -> None:
        http = AsyncCodeFirstHttpClient()
        client = _async_client(http)
        agent = Agent(
            name="Async streaming support",
            instructions="Answer clearly.",
            model="support-fast",
        )

        stream = client.stream(
            agent,
            input="Hello",
            run_config=RunConfig(tracing_disabled=True),
        )
        events = [event async for event in stream]

        assert events
        assert events[0].type == "run.started"
        assert events[-1].type == "run.completed"
        assert stream.result.execution == "local"
        assert stream.final_output == "Streamed response."
        assert http.calls[0][1] == "/models/responses/stream"

    asyncio.run(run())
