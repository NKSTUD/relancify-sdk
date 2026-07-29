# Relancify SDK (Python)

Official Python SDK for the Relancify API.

## Installation

```bash
pip install relancify-sdk
```

## Quickstart

```python
from agents import Agent
from relancify_sdk import RelancifyClient

client = RelancifyClient(api_key="<your_api_key>")

agent = Agent(
    name="Support",
    instructions="Help customers with their orders.",
    model="support-fast",
)

result = client.invoke(agent, input="Where is my order?")
print(result.final_output)

client.close()
```

The model name is a public Relancify catalog key. The SDK uses the OpenAI
Agents SDK `0.19.1` as the local orchestrator, while Relancify selects the
provider and manages its credentials, usage, and billing.

Use `client.models.list()` to discover the public model names and capabilities
available to the current account. Provider routes and credentials are not
exposed.

## Code-first agents

Local Python tools use the native Agents SDK interface:

```python
from agents import Agent, function_tool
from relancify_sdk import RelancifyClient

@function_tool
def get_order_status(order_id: str) -> str:
    """Return an order status from the application's database."""
    return f"Order {order_id} is ready to ship."

client = RelancifyClient(api_key="<your_api_key>")
agent = Agent(
    name="Order support",
    instructions="Use get_order_status when needed.",
    model="support-fast",
    tools=[get_order_status],
)

result = client.invoke(agent, input="Where is order ORD-42?")
print(result.final_output)
```

Use `AsyncRelancifyClient` with `await client.invoke(...)` in async
applications. Both clients also expose `stream(...)`, which yields native
Agents SDK streaming events.

## Available resources

- `client.agents`
- `client.operations`
- `client.models`
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

agent = client.agents.create(
    name="Customer support",
    instructions="Answer clearly using the company knowledge base.",
    model="support-fast",
)

first_turn = client.agents.run_text(
    agent["id"],
    input="How can I reset my password?",
)
second_turn = client.agents.run_text(
    agent["id"],
    input="Can you summarize that?",
    conversation_id=first_turn["conversation_id"],
)

print(second_turn["output"])
print(second_turn["duration_ms"])
client.close()
```

`run_text` and `stream_text` generate a request UUID automatically. An
application may pass `request_id="<uuid>"` when it needs to correlate a call
with its own logs.

For incremental hosted output, iterate over `stream_text`:

```python
for event in client.agents.stream_text(
    agent["id"],
    input="Explain our refund policy.",
):
    if event["event"] == "output.delta":
        print(event["data"]["delta"], end="", flush=True)
```

### Add a hosted HTTP tool

Create the tool once, then attach its public ID to an agent. Relancify keeps
the HTTP configuration server-side and executes the function during hosted
`run_text` and `stream_text` loops.

```python
order_status = client.tools.create_http(
    name="Order status",
    slug="order_status",
    description="Read the current status of an order.",
    method="GET",
    url="https://orders.example.com/orders/{order_id}",
    input_schema={
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
        "additionalProperties": False,
    },
)

agent = client.agents.create_text(
    name="Order assistant",
    instructions="Use order_status when the customer asks about an order.",
    model="support-fast",
    tools=[order_status["public_id"]],
)
```

Hosted HTTP tools can call public HTTP or HTTPS destinations. Private,
loopback, link-local, and cloud metadata destinations are rejected.

### Invoke a registered agent with local Python tools

`invoke` accepts a registered `ag_...` ID directly. It retrieves and briefly
caches the registered definition, while tool execution stays inside the client
process.

```python
from relancify_sdk import RelancifyClient

client = RelancifyClient(api_key="<your_relancify_api_key>")
agent_id = "ag_12345678-1234-1234-1234-123456789abc"

def get_order_status(order_id: str) -> str:
    """Return an order status from the application's own database."""
    return f"Order {order_id} is ready to ship."

result = client.invoke(
    agent_id,
    input="Where is order ORD-42?",
    tools=[get_order_status],
)

print(result.final_output)
client.close()
```

Use `await async_client.invoke(...)` with `AsyncRelancifyClient`.

### Add structured outputs and handoffs

`output_type` and `handoffs` use the native OpenAI Agents SDK loop. Relancify
only proxies each model call through the model configured on the corresponding
Relancify agent. Handoff callbacks, Pydantic validation, guardrails, hooks,
context, and sessions remain in the client application.

```python
from agents import Agent
from pydantic import BaseModel
from relancify_sdk import RelancifyClient

client = RelancifyClient(api_key="<your_relancify_api_key>")

class BillingResolution(BaseModel):
    status: str
    message: str

billing_agent = Agent(
    name="Billing",
    instructions="Resolve billing requests.",
    model="support-precise",
    output_type=BillingResolution,
)

triage_agent = Agent(
    name="Triage",
    instructions="Transfer billing requests to Billing.",
    model="support-fast",
    handoffs=[billing_agent],
)

result = client.invoke(triage_agent, input="My invoice is incorrect.")

print(result.last_agent.name)
print(result.final_output.status)
```

Provider-neutral conversation memory should use an Agents SDK `session`.
`previous_response_id` and `conversation_id` require a Responses API model.
Hosted `prompt` configurations require an OpenAI-native Responses model.
Incompatible routes fail explicitly instead of ignoring those options.

## Notes

- `RelancifyClient` uses synchronous HTTP; `AsyncRelancifyClient` uses
  asynchronous HTTP.
- HTTP errors are raised as `relancify_sdk.errors.ApiError`.
- Runtime websocket connections can use short-lived connect tokens via `client.runtime.create_connect_token(...)`.
- Voice publish flow: create/update a voice agent, call `client.agents.publish(agent_id)`, then poll `client.operations.get(operation_id)`.
- Text agents are managed by Relancify and are ready without a separate provider publish call.
- Text run responses include token usage and the number of Relancify credits debited.
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

## End-to-end examples

Complete individual and multi-agent scenarios for text and voice are available
in [`examples/`](examples/README.md). They cover hosted text runs, true SSE
streaming, native Agents SDK handoffs, voice publication, runtime sessions, and
pre-call multi-agent voice routing.
