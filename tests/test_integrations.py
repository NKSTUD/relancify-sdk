from relancify_sdk.resources.integrations import IntegrationsResource


class RecordingHttpClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, path, json=None):
        self.calls.append((method, path, json))
        return {"public_id": "intg_123"}


def test_upsert_stripe_connection_keeps_secret_in_api_payload_only() -> None:
    http = RecordingHttpClient()
    integrations = IntegrationsResource(http)

    integrations.upsert_stripe_connection(
        name="Production Stripe",
        api_key="sk_live_secret",
        allowed_tools=["list_customers"],
    )

    assert http.calls == [
        (
            "PUT",
            "/integrations/templates/stripe/connection",
            {
                "name": "Production Stripe",
                "api_key": "sk_live_secret",
                "allowed_tools": ["list_customers"],
            },
        )
    ]
