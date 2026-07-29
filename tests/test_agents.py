import unittest
from uuid import UUID

from relancify_sdk.resources.agents import AgentsResource


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


if __name__ == "__main__":
    unittest.main()
