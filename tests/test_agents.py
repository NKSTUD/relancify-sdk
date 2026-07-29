import unittest
from uuid import UUID

from pydantic import BaseModel

from relancify_sdk.resources.agents import AgentsResource


class RecordingHttpClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        return {"id": "ag_123"}


def _model_response(output, response_id):
    return {
        "response": {
            "output": output,
            "usage": {
                "requests": 1,
                "input_tokens": 2,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 1,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 3,
                "request_usage_entries": [],
            },
            "response_id": response_id,
            "request_id": None,
        }
    }


class LocalToolHttpClient:
    def __init__(self) -> None:
        self.calls = []
        self.model_call_count = 0

    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        if method == "GET":
            return {
                "name": "Calculator",
                "modality": "text",
                "prompt": {"system": "Use the calculator tool."},
                "llm": {"model": "support-fast", "temperature": 0.1},
            }

        self.model_call_count += 1
        if self.model_call_count == 1:
            return _model_response(
                [
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "add",
                        "arguments": '{"left":2,"right":3}',
                        "status": "completed",
                    }
                ],
                "resp_1",
            )
        return _model_response(
            [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "The result is 5.",
                            "annotations": [],
                        }
                    ],
                }
            ],
            "resp_2",
        )


class NativeOrchestrationHttpClient:
    def __init__(self, triage_agent_id, billing_agent_id) -> None:
        self.calls = []
        self.triage_agent_id = triage_agent_id
        self.billing_agent_id = billing_agent_id

    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        if method == "GET" and path.endswith(self.triage_agent_id):
            return {
                "name": "Triage",
                "modality": "text",
                "prompt": {"system": "Route billing requests."},
                "llm": {"model": "support-fast"},
            }
        if method == "GET" and path.endswith(self.billing_agent_id):
            return {
                "name": "Billing",
                "modality": "text",
                "prompt": {"system": "Resolve billing requests."},
                "llm": {"model": "support-precise"},
            }
        if method == "POST" and self.triage_agent_id in path:
            return _model_response(
                [
                    {
                        "type": "function_call",
                        "id": "fc_handoff",
                        "call_id": "call_handoff",
                        "name": "transfer_to_billing",
                        "arguments": "{}",
                        "status": "completed",
                    }
                ],
                "resp_triage",
            )
        if method == "POST" and self.billing_agent_id in path:
            return _model_response(
                [
                    {
                        "type": "message",
                        "id": "msg_billing",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"status":"resolved",'
                                    '"message":"Invoice corrected."}'
                                ),
                                "annotations": [],
                            }
                        ],
                    }
                ],
                "resp_billing",
            )
        raise AssertionError(f"Unexpected request: {method} {path}")


class BillingResolution(BaseModel):
    status: str
    message: str


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

    def test_run_local_executes_plain_python_tool_in_client_process(self) -> None:
        http = LocalToolHttpClient()
        resource = AgentsResource(http)
        agent_id = "ag_12345678-1234-1234-1234-123456789abc"
        invocations = []

        def add(left: int, right: int) -> int:
            """Add two integers."""
            invocations.append((left, right))
            return left + right

        result = resource.run_local(
            agent_id,
            input="What is 2 + 3?",
            tools=[add],
        )

        self.assertEqual(result.final_output, "The result is 5.")
        self.assertEqual(invocations, [(2, 3)])
        self.assertEqual(http.model_call_count, 2)
        first_model_payload = http.calls[1][2]
        UUID(first_model_payload["request_id"])
        self.assertEqual(first_model_payload["tools"][0]["name"], "add")
        self.assertEqual(first_model_payload["model_settings"]["temperature"], 0.1)
        self.assertIn(
            "left", first_model_payload["tools"][0]["parameters"]["properties"]
        )
        second_model_payload = http.calls[2][2]
        self.assertTrue(
            any(
                item.get("type") == "function_call_output" and item.get("output") == "5"
                for item in second_model_payload["input"]
            )
        )

    def test_run_local_supports_native_handoff_and_structured_output(self) -> None:
        triage_agent_id = "ag_12345678-1234-1234-1234-123456789abc"
        billing_agent_id = "ag_22345678-1234-1234-1234-123456789abc"
        http = NativeOrchestrationHttpClient(
            triage_agent_id,
            billing_agent_id,
        )
        resource = AgentsResource(http)
        billing_agent = resource.build_local_agent(
            billing_agent_id,
            output_type=BillingResolution,
        )

        result = resource.run_local(
            triage_agent_id,
            input="My invoice is incorrect.",
            handoffs=[billing_agent],
            prompt={"id": "pmpt_support_router", "version": "2"},
            conversation_id="conv_support",
        )

        self.assertEqual(
            result.final_output,
            BillingResolution(
                status="resolved",
                message="Invoice corrected.",
            ),
        )
        self.assertEqual(result.last_agent.name, "Billing")

        triage_payload = next(
            payload
            for method, path, payload in http.calls
            if method == "POST" and triage_agent_id in path
        )
        self.assertEqual(
            triage_payload["system_instructions"],
            "Route billing requests.",
        )
        self.assertEqual(
            triage_payload["handoffs"][0]["tool_name"],
            "transfer_to_billing",
        )
        self.assertEqual(
            triage_payload["prompt"],
            {"id": "pmpt_support_router", "version": "2"},
        )
        self.assertEqual(triage_payload["conversation_id"], "conv_support")

        billing_payload = next(
            payload
            for method, path, payload in http.calls
            if method == "POST" and billing_agent_id in path
        )
        self.assertEqual(
            billing_payload["system_instructions"],
            "Resolve billing requests.",
        )
        self.assertEqual(
            billing_payload["output_schema"]["name"],
            "BillingResolution",
        )
        self.assertEqual(
            billing_payload["output_schema"]["json_schema"]["required"],
            ["status", "message"],
        )


if __name__ == "__main__":
    unittest.main()
