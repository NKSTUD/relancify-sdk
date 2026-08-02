import unittest

from relancify_sdk.resources.tools import ToolsResource


class RecordingHttpClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        return {
            "public_id": "tool_12345678-1234-1234-1234-123456789abc",
        }


class ToolsResourceTests(unittest.TestCase):
    def test_create_http_sends_complete_tool_definition(self) -> None:
        http = RecordingHttpClient()
        resource = ToolsResource(http)

        result = resource.create_http(
            name="Order status",
            slug="order_status",
            description="Read the current order status.",
            method="get",
            url="https://orders.example.com/orders/{order_id}",
            input_schema={
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
            headers={"Authorization": "Bearer managed-secret"},
            timeout_ms=5000,
        )

        self.assertEqual(
            result["public_id"],
            "tool_12345678-1234-1234-1234-123456789abc",
        )
        self.assertEqual(
            http.calls,
            [
                (
                    "POST",
                    "/tools/",
                    {
                        "name": "Order status",
                        "slug": "order_status",
                        "description": "Read the current order status.",
                        "kind": "http",
                        "status": "active",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "order_id": {"type": "string"},
                            },
                            "required": ["order_id"],
                            "additionalProperties": False,
                        },
                        "http": {
                            "method": "GET",
                            "url": (
                                "https://orders.example.com/orders/{order_id}"
                            ),
                            "timeout_ms": 5000,
                            "headers": {
                                "Authorization": "Bearer managed-secret",
                            },
                        },
                    },
                )
            ],
        )

    def test_invalid_http_method_fails_before_api_request(self) -> None:
        http = RecordingHttpClient()
        resource = ToolsResource(http)

        with self.assertRaisesRegex(ValueError, "Invalid method"):
            resource.create_http(
                name="Order status",
                method="TRACE",
                url="https://orders.example.com/orders",
                input_schema={"type": "object", "properties": {}},
            )

        self.assertEqual(http.calls, [])

    def test_create_mcp_http_sends_remote_server_definition(self) -> None:
        http = RecordingHttpClient()
        resource = ToolsResource(http)

        resource.create_mcp_http(
            name="Billing MCP",
            server_url="https://mcp.example.com/mcp",
            transport_type="streamable_http",
            headers={"Authorization": "Bearer managed-secret"},
            allowed_tools=["lookup_invoice"],
        )

        payload = http.calls[0][2]
        self.assertEqual(payload["kind"], "mcp")
        self.assertEqual(payload["mcp"]["transport"], "http")
        self.assertEqual(
            payload["mcp"]["http"]["server_url"],
            "https://mcp.example.com/mcp",
        )
        self.assertEqual(
            payload["mcp"]["allowed_tools"],
            ["lookup_invoice"],
        )

    def test_create_mcp_stdio_sends_customer_runtime_definition(self) -> None:
        http = RecordingHttpClient()
        resource = ToolsResource(http)

        resource.create_mcp_stdio(
            name="Filesystem MCP",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/data"],
        )

        payload = http.calls[0][2]
        self.assertEqual(payload["mcp"]["transport"], "stdio")
        self.assertEqual(payload["mcp"]["stdio"]["command"], "npx")

    def test_tool_paths_validate_public_ids(self) -> None:
        http = RecordingHttpClient()
        resource = ToolsResource(http)

        with self.assertRaisesRegex(ValueError, "Invalid tool_id"):
            resource.get("tool_invalid")

        self.assertEqual(http.calls, [])


if __name__ == "__main__":
    unittest.main()
