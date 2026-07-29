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
- `client.billing`
- `client.conversations`

## Create a text agent

Relancify resolves the provider and its credentials behind the selected public
model. Application code does not need a provider API key or provider-specific
adapter name.

```python
from relancify_sdk import RelancifyClient

client = RelancifyClient(api_key="<your_relancify_api_key>")

agent = client.agents.create_text(
    name="Customer support",
    instructions="Answer clearly using the company knowledge base.",
    model="support-fast",
)

print(agent["id"])
client.close()
```

## Notes

- The SDK uses synchronous `httpx`.
- HTTP errors are raised as `relancify_sdk.errors.ApiError`.
- Runtime websocket connections can use short-lived connect tokens via `client.runtime.create_connect_token(...)`.
- Voice publish flow: create/update a voice agent, call `client.agents.publish(agent_id)`, then poll `client.operations.get(operation_id)`.
- Text agents are managed by Relancify and are ready without a separate provider publish call.
- Agent IDs use the public format `ag_<uuid>` for all agent endpoints.

## Billing reads

```python
from relancify_sdk import RelancifyClient

client = RelancifyClient(api_key="<your_api_key>")

summary = client.billing.summary()
usage = client.billing.usage_ledger(page=1, page_size=20)
transactions = client.billing.credit_transactions(page=1, page_size=20)

client.close()
```

Returned fields are intentionally user-facing and minimal (plan/status, balances,
period usage totals, and paginated simple history rows). Internal provider-cost
details are not exposed in these tenant endpoints.

## Runtime session

```python
from relancify_sdk import RelancifyClient

agent_id = "ag_12345678-1234-1234-1234-123456789abc"
client = RelancifyClient(api_key="<your_api_key>")

session = client.agents.create_runtime_session(agent_id)
print(session["session_id"])

client.close()
```

## Conversation audio

```python
from relancify_sdk import RelancifyClient

client = RelancifyClient(api_key="<your_api_key>")

conversation_id = "8a922e4f-ede8-499f-a4ec-1a192f096dcf"
audio = client.conversations.get_audio(conversation_id)

filename = audio["filename"] or f"{conversation_id}.mp3"
file = open(filename, "wb")
file.write(audio["audio_bytes"])
file.close()

client.close()
```

## Publish flow

```python
from relancify_sdk import RelancifyClient

agent_id = "ag_12345678-1234-1234-1234-123456789abc"
client = RelancifyClient(api_key="<your_api_key>")

accepted = client.agents.publish(agent_id)
operation = client.operations.get(accepted["operation_id"])

print(operation["status"])

client.close()
```

## Security best practices

- Never hardcode API keys or bearer tokens in source code.
- Use environment variables or a secure secret manager.
- Rotate credentials periodically.
- Prefer short-lived access tokens when possible.
