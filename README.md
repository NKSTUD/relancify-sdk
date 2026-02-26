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
- `client.operations`
- `client.runtime`
- `client.users`
- `client.voices`
- `client.api_keys`

## Notes

- The SDK uses synchronous `httpx`.
- HTTP errors are raised as `relancify_sdk.errors.ApiError`.
- Runtime websocket connections can use short-lived connect tokens via `client.runtime.create_connect_token(...)`.
- Publish flow: create/update agent locally, call `client.agents.publish(agent_id)`, then poll `client.operations.get(operation_id)`.
- Agent IDs use the public format `ag_<uuid>` for all agent endpoints.
- `ApiError` exposes `code`, `scope`, `limit`, `current`, and `retry_after_sec` helpers for rate-limit handling.

## Runtime backpressure handling (recommended)

Use bounded retry when `create_runtime_session` returns `429` or `code` starting with `rate_limit_`.

```python
import random
import time
from relancify_sdk import ApiError

MAX_ATTEMPTS = 3

def create_runtime_session_with_retry(client, agent_id: str):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return client.agents.create_runtime_session(agent_id)
        except ApiError as exc:
            is_rate_limited = exc.status_code == 429 or str(exc.code or "").startswith("rate_limit_")
            if not is_rate_limited or attempt >= MAX_ATTEMPTS:
                raise
            retry_after = exc.retry_after_sec or 1
            time.sleep(retry_after + random.uniform(0, 0.25))
    raise RuntimeError("Unable to create runtime session after retry")
```

## Security best practices

- Never hardcode API keys or bearer tokens in source code.
- Use environment variables or a secure secret manager.
- Rotate credentials periodically.
- Prefer short-lived access tokens when possible.
