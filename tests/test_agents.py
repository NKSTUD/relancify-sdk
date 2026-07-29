import unittest

from relancify_sdk.resources.agents import AgentsResource


class RecordingHttpClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        return {"id": "ag_123"}


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


if __name__ == "__main__":
    unittest.main()
