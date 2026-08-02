import asyncio
import unittest
from types import SimpleNamespace
from uuid import UUID

from relancify_sdk import AsyncRelancify, Relancify
from relancify_sdk.client import AsyncRelancifyClient, RelancifyClient
from relancify_sdk.resources.agents import AgentsResource, AsyncAgentsResource
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
from relancify_sdk.streaming import _normalize_local_event


class RecordingHttpClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        return {"id": "ag_123"}


class StreamingHttpClient(RecordingHttpClient):
    def stream_lines(self, method, path, json=None):
        self.calls.append((method, path, json))
        yield "event: run.started"
        yield 'data: {"id":"run_1"}'
        yield ""
        yield "event: output.delta"
        yield 'data: {"delta":"Hello"}'
        yield ""
        yield "event: run.completed"
        yield 'data: {"output":"Hello","billing":{"credits_debited":1}}'
        yield ""


class HostedRunHttpClient(StreamingHttpClient):
    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        return {
            "id": "66785332-89b0-4813-8f47-371b9e58df41",
            "output": "Hello",
            "conversation_id": "c9a2ecba-cadc-4f63-9dff-95f1da24dcee",
            "usage": {"total_tokens": 5},
            "billing": {"credits_debited": 1},
        }


class AsyncHostedRunHttpClient:
    def __init__(self) -> None:
        self.calls = []

    async def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        return {
            "output": "Hello async",
            "conversation_id": "c9a2ecba-cadc-4f63-9dff-95f1da24dcee",
            "usage": {"total_tokens": 6},
            "billing": {"credits_debited": 2},
        }

    async def stream_lines(self, method, path, json=None):
        self.calls.append((method, path, json))
        for line in (
            "event: run.started",
            'data: {"id":"run_1"}',
            "",
            "event: output.delta",
            'data: {"delta":"Hello async"}',
            "",
            "event: run.completed",
            'data: {"output":"Hello async","billing":{"credits_debited":2}}',
            "",
        ):
            yield line


class ErrorStreamingHttpClient(RecordingHttpClient):
    def stream_lines(self, method, path, json=None):
        self.calls.append((method, path, json))
        yield "event: run.started"
        yield 'data: {"id":"run_1"}'
        yield ""
        yield "event: error"
        yield (
            'data: {"code":"billing.insufficient_credits",'
            '"message":"Insufficient credits"}'
        )
        yield ""


class AgentsResourceTests(unittest.TestCase):
    def test_public_client_names_are_short_aliases(self) -> None:
        self.assertIs(Relancify, RelancifyClient)
        self.assertIs(AsyncRelancify, AsyncRelancifyClient)
        self.assertEqual(Relancify.__name__, "Relancify")
        self.assertEqual(AsyncRelancify.__name__, "AsyncRelancify")

    def test_create_accepts_simple_text_agent_fields(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)

        resource.create(
            name="Customer support",
            instructions="Answer clearly.",
            model="support-fast",
        )

        self.assertEqual(http.calls[0][1], "/agents")
        self.assertEqual(http.calls[0][2]["modality"], "text")
        self.assertEqual(http.calls[0][2]["llm"]["model"], "support-fast")

    def test_create_voice_uses_models_and_capabilities_without_providers(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)
        capability_id = "intg_12345678-1234-1234-1234-123456789abc"

        resource.create(
            name="French voice support",
            interaction_mode="voice",
            instructions="Réponds en français.",
            llm_model="support-fast",
            stt_model="speech-fr-realtime",
            tts_model="speech-natural-v2",
            voice="voice_fr_natural",
            language="fr",
            capabilities=[capability_id],
        )

        payload = http.calls[0][2]
        self.assertEqual(payload["modality"], "voice")
        self.assertEqual(payload["llm"], {"model": "support-fast"})
        self.assertEqual(payload["stt"]["model"], "speech-fr-realtime")
        self.assertEqual(payload["tts"]["model"], "speech-natural-v2")
        self.assertEqual(payload["tts"]["voice_id"], "voice_fr_natural")
        self.assertNotIn("primary_provider", payload)
        self.assertNotIn("provider", payload["llm"])
        self.assertNotIn("runtime", payload)
        self.assertEqual(payload["tools"], [{"id": capability_id, "required": False}])

    def test_create_rejects_fields_incompatible_with_interaction_mode(self) -> None:
        resource = AgentsResource(RecordingHttpClient())

        with self.assertRaisesRegex(TypeError, "Chat agents cannot define"):
            resource.create(
                name="Invalid chat",
                interaction_mode="chat",
                instructions="Answer.",
                model="support-fast",
                voice="voice_123",
            )

    def test_create_rejects_mixing_raw_payload_and_named_fields(self) -> None:
        resource = AgentsResource(RecordingHttpClient())

        with self.assertRaisesRegex(TypeError, "either a complete payload"):
            resource.create(
                {"name": "Raw agent"},
                status="active",
            )

    def test_create_text_sends_minimal_provider_independent_payload(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)

        result = resource.create_text(
            name="Customer support",
            instructions="Answer clearly.",
            model="support-fast",
        )

        self.assertEqual(result, {"id": "ag_123"})
        self.assertEqual(
            http.calls,
            [
                (
                    "POST",
                    "/agents",
                    {
                        "name": "Customer support",
                        "status": "draft",
                        "modality": "text",
                        "prompt": {
                            "system": "Answer clearly.",
                            "rag_enabled": True,
                        },
                        "llm": {"model": "support-fast"},
                    },
                )
            ],
        )

    def test_create_text_includes_only_explicit_optional_values(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)

        resource.create_text(
            name="Customer support",
            instructions="Answer clearly.",
            model="support-fast",
            status="active",
            rag_enabled=False,
            temperature=0.3,
            session={"language": "fr"},
        )

        payload = http.calls[0][2]
        self.assertEqual(payload["status"], "active")
        self.assertFalse(payload["prompt"]["rag_enabled"])
        self.assertEqual(payload["llm"]["temperature"], 0.3)
        self.assertEqual(payload["session"], {"language": "fr"})

    def test_create_text_attaches_registered_tools_by_public_id(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)
        tool_id = "tool_12345678-1234-1234-1234-123456789abc"

        resource.create_text(
            name="Customer support",
            instructions="Check order status when needed.",
            model="support-fast",
            tools=[tool_id],
        )

        self.assertEqual(
            http.calls[0][2]["tools"],
            [{"id": tool_id, "required": False}],
        )

    def test_create_text_attaches_site_integration_by_public_id(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)
        integration_id = "intg_12345678-1234-1234-1234-123456789abc"

        resource.create_text(
            name="Billing support",
            instructions="Use Stripe when needed.",
            model="support-fast",
            tools=[integration_id],
        )

        self.assertEqual(
            http.calls[0][2]["tools"],
            [{"id": integration_id, "required": False}],
        )

    def test_create_text_serializes_declarative_skills(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)

        resource.create_text(
            name="Billing support",
            instructions="Answer clearly.",
            model="support-fast",
            skills=[
                {
                    "name": "Billing",
                    "description": "Handles invoices.",
                    "instructions": "Verify invoices.",
                }
            ],
        )

        self.assertEqual(
            http.calls[0][2]["skills"],
            [
                {
                    "name": "Billing",
                    "description": "Handles invoices.",
                    "instructions": "Verify invoices.",
                    "enabled": True,
                }
            ],
        )

    def test_run_text_can_continue_a_conversation(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)
        agent_id = "ag_12345678-1234-1234-1234-123456789abc"
        request_id = "66785332-89b0-4813-8f47-371b9e58df41"

        resource.run_text(
            agent_id,
            input="Continue",
            conversation_id="c9a2ecba-cadc-4f63-9dff-95f1da24dcee",
            request_id=request_id,
        )

        self.assertEqual(
            http.calls,
            [
                (
                    "POST",
                    f"/agents/{agent_id}/runs",
                    {
                        "request_id": request_id,
                        "input": "Continue",
                        "conversation_id": "c9a2ecba-cadc-4f63-9dff-95f1da24dcee",
                    },
                )
            ],
        )

    def test_stream_text_parses_stable_sse_events(self) -> None:
        http = StreamingHttpClient()
        resource = AgentsResource(http)
        agent_id = "ag_12345678-1234-1234-1234-123456789abc"
        request_id = "66785332-89b0-4813-8f47-371b9e58df41"

        events = list(
            resource.stream_text(
                agent_id,
                input="Hello",
                request_id=request_id,
            )
        )

        self.assertEqual(
            [event["event"] for event in events],
            ["run.started", "output.delta", "run.completed"],
        )
        self.assertEqual(events[1]["data"]["delta"], "Hello")
        self.assertEqual(
            events[-1]["data"]["billing"]["credits_debited"],
            1,
        )
        self.assertEqual(http.calls[0][2]["request_id"], request_id)

    def test_stream_text_raises_on_error_event(self) -> None:
        http = ErrorStreamingHttpClient()
        resource = AgentsResource(http)
        agent_id = "ag_12345678-1234-1234-1234-123456789abc"

        with self.assertRaises(RuntimeError) as ctx:
            list(resource.stream_text(agent_id, input="Hello"))

        self.assertEqual(str(ctx.exception), "Insufficient credits")

    def test_hosted_text_runs_generate_request_ids_by_default(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)
        agent_id = "ag_12345678-1234-1234-1234-123456789abc"

        resource.run_text(agent_id, input="Hello")

        UUID(http.calls[0][2]["request_id"])

    def test_client_run_defaults_registered_ids_to_hosted_execution(self) -> None:
        http = HostedRunHttpClient()
        client = object.__new__(RelancifyClient)
        client.agents = AgentsResource(http)
        agent_id = "ag_12345678-1234-1234-1234-123456789abc"

        result = client.run(agent_id, "Hello")

        self.assertEqual(result.output, "Hello")
        self.assertEqual(result.final_output, "Hello")
        self.assertEqual(result.execution, "hosted")
        self.assertEqual(result.billing["credits_debited"], 1)
        self.assertEqual(http.calls[0][1], f"/agents/{agent_id}/runs")

    def test_client_stream_normalizes_hosted_events(self) -> None:
        http = HostedRunHttpClient()
        client = object.__new__(RelancifyClient)
        client.agents = AgentsResource(http)
        agent_id = "ag_12345678-1234-1234-1234-123456789abc"

        stream = client.stream(agent_id, "Hello")
        events = list(stream)

        self.assertEqual(
            [event.type for event in events],
            ["run.started", "output.delta", "run.completed"],
        )
        self.assertEqual(events[1].delta, "Hello")
        self.assertEqual(stream.result.output, "Hello")
        self.assertEqual(stream.result.execution, "hosted")

    def test_closed_stream_cannot_be_consumed_again(self) -> None:
        http = HostedRunHttpClient()
        client = object.__new__(RelancifyClient)
        client.agents = AgentsResource(http)
        agent_id = "ag_12345678-1234-1234-1234-123456789abc"
        stream = client.stream(agent_id, "Hello")

        stream.close()

        with self.assertRaises(StopIteration):
            next(stream)

    def test_function_argument_delta_is_not_exposed_as_output_text(self) -> None:
        raw = SimpleNamespace(
            type="raw_response_event",
            data=SimpleNamespace(
                type="response.function_call_arguments.delta",
                delta='{"order_id":',
            ),
        )

        event = _normalize_local_event(raw)

        self.assertEqual(event.type, "run.event")
        self.assertIsNone(event.delta)
        self.assertEqual(
            event.data["native_type"],
            "response.function_call_arguments.delta",
        )


class AsyncAgentsResourceTests(unittest.TestCase):
    def test_async_resources_keep_sync_method_parity(self) -> None:
        public = lambda cls: {
            name
            for name, value in cls.__dict__.items()
            if callable(value) and not name.startswith("_")
        }

        resource_pairs = (
            (AgentsResource, AsyncAgentsResource),
            (ApiKeysResource, AsyncApiKeysResource),
            (BillingResource, AsyncBillingResource),
            (ConversationsResource, AsyncConversationsResource),
            (IntegrationsResource, AsyncIntegrationsResource),
            (ModelsResource, AsyncModelsResource),
            (OperationsResource, AsyncOperationsResource),
            (RuntimeResource, AsyncRuntimeResource),
            (ToolsResource, AsyncToolsResource),
            (UsersResource, AsyncUsersResource),
            (VoicesResource, AsyncVoicesResource),
        )
        for sync_resource, async_resource in resource_pairs:
            with self.subTest(resource=sync_resource.__name__):
                self.assertEqual(public(sync_resource), public(async_resource))

    def test_async_client_has_hosted_run_and_stream_parity(self) -> None:
        async def run_test() -> None:
            http = AsyncHostedRunHttpClient()
            client = object.__new__(AsyncRelancifyClient)
            client.agents = AsyncAgentsResource(http)
            agent_id = "ag_12345678-1234-1234-1234-123456789abc"

            result = await client.run(agent_id, "Hello")
            stream = client.stream(agent_id, "Hello")
            events = [event async for event in stream]

            self.assertEqual(result.output, "Hello async")
            self.assertEqual(result.execution, "hosted")
            self.assertEqual(events[1].delta, "Hello async")
            self.assertEqual(stream.result.output, "Hello async")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
