# Relancify SDK (Python)

Official Python SDK for the Relancify API.

## Installation

```bash
pip install relancify-sdk
```

## Quickstart

```python
from relancify_sdk import RelancifyClient

client = RelancifyClient(
    base_url="https://api.relancify.com/api/v1",
    api_key="<your_api_key>",
)

agents = client.agents.list()
print(len(agents))

client.close()
```

## Available resources

- `client.agents`
- `client.runtime`
- `client.users`
- `client.voices`
- `client.api_keys`

## Notes

- The SDK uses synchronous `httpx`.
- HTTP errors are raised as `relancify_sdk.errors.ApiError`.

## Security best practices

- Never hardcode API keys or bearer tokens in source code.
- Use environment variables or a secure secret manager.
- Rotate credentials periodically.
- Prefer short-lived access tokens when possible.
