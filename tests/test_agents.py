import unittest
from uuid import UUID

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


class AgentsResourceTests(unittest.TestCase):
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

    def test_run_text_can_continue_a_conversation(self) -> None:
        http = RecordingHttpClient()
        resource = AgentsResource(http)
        agent_id = "ag_12345678-1234-1234-1234-123456789abc"

        resource.run_text(
            agent_id,
            input="Continue",
            conversation_id="c9a2ecba-cadc-4f63-9dff-95f1da24dcee",
        )

        self.assertEqual(
            http.calls,
            [
                (
                    "POST",
                    f"/agents/{agent_id}/runs",
                    {
                        "input": "Continue",
                        "conversation_id": "c9a2ecba-cadc-4f63-9dff-95f1da24dcee",
                    },
                )
            ],
        )

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
        self.assertIn("left", first_model_payload["tools"][0]["parameters"]["properties"])
        second_model_payload = http.calls[2][2]
        self.assertTrue(
            any(
                item.get("type") == "function_call_output"
                and item.get("output") == "5"
                for item in second_model_payload["input"]
            )
        )


if __name__ == "__main__":
    unittest.main()
