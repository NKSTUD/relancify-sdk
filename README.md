# Relancify SDK for Python

The official Python SDK for building, running, and operating Relancify text and
voice agents.

Relancify provides the model gateway, provider credentials, usage metering,
billing, hosted text execution, voice runtime control plane, and a local
orchestration layer for tools, structured outputs, guardrails, and multi-agent
handoffs.

## Requirements

- Python 3.10 or newer
- A Relancify workspace
- A Relancify API key with the scopes required by your integration
- Workspace credits and at least one active model in the Relancify catalog

## Installation

```bash
python -m pip install --upgrade relancify-sdk
```

Check the installed version:

```bash
python -c "import relancify_sdk; print(relancify_sdk.__version__)"
```

## Authentication

Create an API key from the Relancify developer settings. Keep it in an
environment variable or a secret manager:

```bash
export RELANCIFY_API_KEY="your-relancify-api-key"
```

The SDK does not read this variable automatically. Pass it to the client:

```python
import os

from relancify_sdk import RelancifyClient

client = RelancifyClient(
    api_key=os.environ["RELANCIFY_API_KEY"],
)
```

The production API URL is used by default. Override it only when connecting to
a local or self-hosted Relancify API:

```python
client = RelancifyClient(
    api_key=os.environ["RELANCIFY_API_KEY"],
    base_url=os.getenv(
        "RELANCIFY_BASE_URL",
        "https://api.relancify.com/api/v1",
    ),
    timeout=60.0,
)
```

Non-local API URLs must use HTTPS. Redirects are deliberately not followed, so
credentials cannot be forwarded to an unexpected host.

### API key scopes

Use the smallest set of scopes required by the application:

| Scope | Typical operations |
| --- | --- |
| `agent:read` | List/read agents, models, tools, conversations, operations, and runtime sessions |
| `agent:write` | Create/update/delete agents and tools, run models, publish agents, and create/close runtime sessions |
| `voice:read` | Read the voice catalog |
| `voice:write` | Modify voice resources when the API operation supports it |
| `billing:read` | Read workspace billing summary and usage history |

Most text integrations need `agent:read` and `agent:write`. Voice integrations
normally also need `voice:read`.

## Choose the correct execution mode

Relancify supports three complementary patterns:

| Pattern | Use it when | Main methods |
| --- | --- | --- |
| Hosted text agent | The saved Relancify agent owns its prompt, model, hosted tools, and conversation | `create_text`, `run_text`, `stream_text` |
| Code-first agent | Your Python process owns tools, handoffs, guardrails, context, and orchestration | `invoke`, `stream` |
| Voice agent | Relancify manages the voice runtime while a web/mobile client transports audio | `create`, `publish`, `create_runtime_session` |

`run_text` and `invoke` are intentionally different:

- `run_text` executes a registered text agent entirely through the hosted
  Relancify runtime.
- `invoke` runs a Relancify orchestration loop in your Python application while
  every model request is routed and billed through Relancify.

## Discover an available model

Do not assume that a provider model name is available to every workspace. Use
the public model catalog and store the returned `id` in your application
configuration:

```python
import os

from relancify_sdk import RelancifyClient

with RelancifyClient(
    api_key=os.environ["RELANCIFY_API_KEY"],
) as client:
    catalog = client.models.list(page=1, page_size=100)

    for model in catalog["items"]:
        print(
            model["id"],
            model.get("name"),
            model.get("capabilities", {}),
        )
```

For multi-agent handoffs, select a model whose capabilities include tool
calling. For a Pydantic `output_type`, select a model that supports structured
output.

## Hosted text agents

### Create and run an agent

```python
import os

from relancify_sdk import RelancifyClient

api_key = os.environ["RELANCIFY_API_KEY"]
model_id = os.environ["RELANCIFY_TEXT_MODEL"]

with RelancifyClient(api_key=api_key) as client:
    agent = client.agents.create_text(
        name="Customer support",
        instructions=(
            "Answer customer questions clearly. "
            "If information is missing, say so explicitly."
        ),
        model=model_id,
        status="active",
        rag_enabled=False,
        temperature=0.2,
        session={"language": "en"},
    )

    result = client.agents.run_text(
        agent["id"],
        input="How do I reset my password?",
    )

    print(result["output"])
    print(result["conversation_id"])
    print(result["usage"])
    print(result["billing"])
```

Agent IDs always use the public `ag_<uuid>` format.

### Continue a conversation

Pass the first response's `conversation_id` to the next turn:

```python
second_turn = client.agents.run_text(
    agent["id"],
    input="Summarize that answer in one sentence.",
    conversation_id=result["conversation_id"],
)
```

`run_text` creates a request UUID automatically. Pass your own UUID with
`request_id` when correlating the call with application logs:

```python
response = client.agents.run_text(
    agent["id"],
    input="Hello",
    request_id="3e41d587-d72c-4b41-8998-b06c750a9117",
)
```

### Stream real output

`stream_text` consumes the hosted Server-Sent Events stream and yields parsed
events as they arrive:

```python
for event in client.agents.stream_text(
    agent["id"],
    input="Explain the refund policy.",
):
    if event["event"] == "output.delta":
        print(event["data"]["delta"], end="", flush=True)
    elif event["event"] == "run.completed":
        completed = event["data"]
        print()
        print(completed["usage"])
        print(completed["billing"])
```

Important events:

| Event | Meaning |
| --- | --- |
| `output.delta` | Incremental text generated by the model |
| `run.completed` | Final usage, billing, and conversation metadata |
| `error` | The stream failed; iteration raises an exception |

Render the accumulated output as Markdown in your UI. The SDK returns model
text; it does not inject HTML or render Markdown itself.

### Attach a hosted HTTP tool

A hosted tool is configured on Relancify and executed by the hosted
`run_text`/`stream_text` loop:

```python
order_status = client.tools.create_http(
    name="Order status",
    slug="order_status",
    description="Return the current status of an order.",
    method="GET",
    url="https://orders.example.com/orders/{order_id}",
    input_schema={
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
        },
        "required": ["order_id"],
        "additionalProperties": False,
    },
    timeout_ms=10_000,
)

agent = client.agents.create_text(
    name="Order assistant",
    instructions="Use order_status when a customer asks about an order.",
    model=model_id,
    status="active",
    tools=[order_status["public_id"]],
)
```

Hosted HTTP tools may call public HTTP or HTTPS destinations. Relancify rejects
loopback, private-network, link-local, and cloud metadata destinations.

## Code-first agents

Use code-first agents when the application process must own tool execution,
guardrails, context, sessions, or handoff logic.

### Local Python tool

```python
import os

from relancify_sdk import Agent, RelancifyClient, function_tool


@function_tool
def get_order_status(order_id: str) -> str:
    """Return an order status from the application's database."""
    return f"Order {order_id} is ready to ship."


agent = Agent(
    name="Order support",
    instructions="Use get_order_status when the customer provides an order ID.",
    model=os.environ["RELANCIFY_TEXT_MODEL"],
    tools=[get_order_status],
)

with RelancifyClient(
    api_key=os.environ["RELANCIFY_API_KEY"],
) as client:
    result = client.invoke(
        agent,
        input="Where is order ORD-42?",
    )
    print(result.final_output)
```

The Python tool runs in your process. Relancify receives the model request and
tool schema, but does not execute your local function.

### Invoke a registered agent with local tools

Pass an existing text agent ID instead of constructing an `Agent`. The SDK
loads the saved prompt and model, then adds the local orchestration options:

```python
def get_account_status(customer_id: str) -> str:
    """Read an account status from the local application."""
    return f"Customer {customer_id} is active."


result = client.invoke(
    "ag_12345678-1234-1234-1234-123456789abc",
    input="Check customer C-42.",
    tools=[get_account_status],
)
```

Registered agent definitions are cached for 30 seconds by default. Updates,
deletes, and publishes performed through the same client invalidate the cache.
Use `agent_cache_ttl=0` to disable caching or call
`client.clear_agent_cache(agent_id)`.

Only registered text agents can be passed to `invoke`.

### Structured output

```python
from typing import Literal

from pydantic import BaseModel
from relancify_sdk import Agent


class RequestRoute(BaseModel):
    destination: Literal["billing", "technical"]
    reason: str


router = Agent(
    name="Request router",
    instructions=(
        "Choose billing for invoice and payment questions. "
        "Choose technical for product incidents."
    ),
    model=os.environ["RELANCIFY_TEXT_MODEL"],
    output_type=RequestRoute,
)

result = client.invoke(router, input="My invoice amount is incorrect.")
route: RequestRoute = result.final_output
print(route.destination)
```

The selected model must advertise structured-output support in
`client.models.list()`.

### Multi-agent handoffs

```python
import os

from relancify_sdk import Agent

model_id = os.environ["RELANCIFY_TEXT_MODEL"]

billing_agent = Agent(
    name="Billing specialist",
    instructions="Resolve billing questions.",
    model=model_id,
)

technical_agent = Agent(
    name="Technical specialist",
    instructions="Diagnose technical problems.",
    model=model_id,
)

triage_agent = Agent(
    name="Triage",
    instructions=(
        "Always hand the request to the most relevant specialist. "
        "Do not answer the request yourself."
    ),
    model=model_id,
    handoffs=[billing_agent, technical_agent],
)

result = client.invoke(
    triage_agent,
    input="The application crashes when I sign in.",
    max_turns=5,
)

print(result.last_agent.name)
print(result.final_output)
```

Handoffs require a model with tool-calling support. The orchestration loop and
handoff callbacks run inside your Python application.

### Stream a code-first run

`client.stream(...)` yields Relancify orchestration events:

```python
for event in client.stream(agent, input="Count from one to five."):
    print(event)
```

This stream is different from `client.agents.stream_text(...)`:

- `client.stream` exposes orchestration events for a local Relancify agent
  loop.
- `client.agents.stream_text` exposes stable hosted Relancify text events.

### Conversation memory

Use a compatible `session` object for provider-neutral code-first memory.
`previous_response_id` and `conversation_id` are only compatible with model
routes that implement server-managed response state. Hosted `prompt`
configurations also require a compatible model route. Incompatible routes fail
explicitly.

## Async client

Use `AsyncRelancifyClient` for asynchronous model orchestration and the async
agent/model resources:

```python
import asyncio
import os

from relancify_sdk import Agent, AsyncRelancifyClient


async def main() -> None:
    agent = Agent(
        name="Async assistant",
        instructions="Answer concisely.",
        model=os.environ["RELANCIFY_TEXT_MODEL"],
    )

    async with AsyncRelancifyClient(
        api_key=os.environ["RELANCIFY_API_KEY"],
    ) as client:
        result = await client.invoke(agent, input="Say hello.")
        print(result.final_output)

        async for event in client.stream(agent, input="Count to three."):
            print(event)


asyncio.run(main())
```

The async client currently exposes `agents`, `models`, `invoke`, and `stream`.
Use the synchronous client for the complete resource surface, including hosted
text runs, tools, billing, voice runtime operations, and conversations.

## Voice agents

The Python SDK manages the voice control plane:

1. Discover models and voices.
2. Create the voice agent configuration.
3. Publish it when the selected direct provider requires publication.
4. Create a runtime session.
5. Give the returned connection option to a web, mobile, or telephony audio
   client.
6. Close the runtime session when finished.

The SDK does not capture microphone audio or join a WebRTC room.

### Create a voice agent

The exact STT, TTS, and LLM values depend on your Relancify catalog. The
following example expects catalog values in environment variables:

```python
import os

from relancify_sdk import RelancifyClient

payload = {
    "name": "French voice support",
    "status": "active",
    "modality": "voice",
    "primary_provider": "livekit",
    "prompt": {
        "system": "You are a concise French customer-support agent.",
        "rag_enabled": False,
    },
    "session": {
        "first_message": "Bonjour, comment puis-je vous aider ?",
        "language": "fr",
        "allow_interruptions": True,
        "disable_first_message_interruptions": True,
        "max_duration_seconds": 300,
        "client_events": [
            "interruption",
            "user_transcript",
            "agent_response",
        ],
    },
    "llm": {
        "model": os.environ["RELANCIFY_VOICE_LLM_MODEL"],
        "temperature": 0.2,
    },
    "stt": {
        "provider": os.environ["RELANCIFY_VOICE_STT_PROVIDER"],
        "model": os.environ["RELANCIFY_VOICE_STT_MODEL"],
        "language": "fr",
    },
    "tts": {
        "provider": os.environ["RELANCIFY_VOICE_TTS_PROVIDER"],
        "model": os.environ["RELANCIFY_VOICE_TTS_MODEL"],
        "voice_id": os.environ["RELANCIFY_VOICE_ID"],
        "language": "fr",
        "voice": {"speed": 1.0},
    },
    "tools": [],
    "runtime": {
        "provider": "livekit",
        "livekit": {
            "room_prefix": "my-application",
            "session": {"preemptive_generation": True},
        },
    },
}

with RelancifyClient(
    api_key=os.environ["RELANCIFY_API_KEY"],
) as client:
    voice_agent = client.agents.create(payload)
    print(voice_agent["id"])
```

Use `client.voices.list()` to discover valid voice IDs and their compatible TTS
models. Use `client.models.list()` to discover valid LLM IDs.

### Publish and wait

LiveKit agents are ready without a separate provider publication. Direct
OpenAI and ElevenLabs runtimes may require:

```python
import time

accepted = client.agents.publish(voice_agent["id"])
operation_id = accepted["operation_id"]

while True:
    operation = client.operations.get(operation_id)
    if operation["status"] in {"ready", "failed"}:
        break
    time.sleep(1)

if operation["status"] != "ready":
    raise RuntimeError(operation.get("error_detail", "Voice publish failed"))
```

### Open and close a runtime session

```python
session = client.agents.create_runtime_session(voice_agent["id"])
session_id = session.get("runtime_session_id") or session["session_id"]

for option in session["connection"]["options"]:
    print(option["transport"], option["url"], option["auth"]["type"])

# Connect the audio client here.

client.runtime.close_session(session_id)
```

LiveKit normally returns a WebRTC connection option with a participant token.
Do not log or persist that token.

For direct OpenAI or ElevenLabs relay sessions, create a short-lived connect
token and build the WebSocket URL:

```python
token = client.runtime.create_connect_token(session_id)
websocket_url = client.runtime.build_websocket_url(
    session_id,
    connect_token=token["connect_token"],
)
```

Never expose a long-lived workspace API key to a browser or mobile client.

### Multi-agent voice routing

A common architecture routes the initial request before opening audio:

```text
initial request -> structured text router -> selected voice agent
                                       |--> sales
                                       '--> support
```

This is pre-call routing. Moving an already-open call between agents requires a
runtime handoff tool supported and configured for the selected voice provider.

## Error handling

HTTP failures raise `ApiError`:

```python
from relancify_sdk import ApiError

try:
    result = client.agents.run_text(agent_id, input="Hello")
except ApiError as error:
    print("status:", error.status_code)
    print("code:", error.code)
    print("scope:", error.scope)
    print("retry after:", error.retry_after_sec)
    print("detail:", error.payload)
```

The SDK automatically retries HTTP `429` responses up to two times and respects
`Retry-After`, capped at 10 seconds per retry. Applications should still handle
a final `429`.

Common failures:

| Symptom | What to check |
| --- | --- |
| `401` | The key is missing, expired, revoked, or sent to the wrong API URL |
| `403 Missing API key scope` | Create a key containing the scope named in `error.scope` |
| `403 API key is not allowed for this endpoint` | The endpoint is user/admin-only or the deployed API predates SDK support |
| `402` or insufficient credits | Add credits or verify the workspace subscription |
| `404 Active pricing entry not found` / billing unavailable | Configure active pricing for the selected managed model |
| Inference model unavailable | Read `client.models.list()` and use a returned public model ID |
| Voice runtime unavailable | Verify runtime credentials, the LiveKit worker, and provider compatibility |
| Structured output or handoff fails | Select a model advertising the required capability |

Do not show raw provider errors or stack traces to end users. Log technical
details server-side and return a safe application message.

## Resource reference

The synchronous client exposes:

| Resource | Public methods |
| --- | --- |
| `client.agents` | `list`, `get`, `create`, `create_text`, `update`, `delete`, `publish`, `run_text`, `stream_text`, `create_runtime_session` |
| `client.models` | `list` |
| `client.tools` | `list`, `get`, `create`, `create_http`, `update`, `delete` |
| `client.operations` | `get` |
| `client.runtime` | `get_session`, `close_session`, `create_connect_token`, `build_websocket_url` |
| `client.voices` | `list` |
| `client.conversations` | `get_audio` |
| `client.billing` | `summary`, `usage_ledger`, `credit_transactions` |
| `client.users` | `me` |
| `client.api_keys` | `list`, `create`, `revoke` |

`users` and API-key administration may require a user bearer token instead of
a workspace API key:

```python
client = RelancifyClient(bearer=user_access_token)
```

## Security checklist

- Never hardcode or commit API keys, bearer tokens, runtime tokens, or provider
  credentials.
- Store server-side credentials in environment variables or a secret manager.
- Never send a Relancify workspace API key to browser or mobile code.
- Grant the minimum API-key scopes and rotate keys periodically.
- Use short-lived runtime connect tokens for untrusted clients.
- Do not log authorization headers, participant tokens, or connect-token query
  parameters.
- Keep production traffic on HTTPS/WSS.
- Validate tool inputs and authorize every local tool call against the current
  user and workspace.
- Treat model output as untrusted text before rendering or using it in another
  system.
- Close clients and voice runtime sessions reliably.

## Integration checklist for coding agents

When integrating this SDK into another project:

1. Install and pin a compatible `relancify-sdk` version.
2. Read credentials from the target project's secret-management system.
3. Create one long-lived client per application lifecycle, not one per request.
4. Discover and configure public model IDs from `client.models.list()`.
5. Choose hosted text, code-first, or voice execution deliberately.
6. Keep hosted HTTP tools and local Python tools conceptually separate.
7. Preserve `conversation_id` for hosted multi-turn text conversations.
8. Handle `ApiError`, timeouts, rate limits, and insufficient credits.
9. Do not expose workspace keys or runtime tokens in logs or client bundles.
10. Add a smoke test using the target workspace before enabling production
    traffic.

Do not bypass the SDK with raw provider credentials. Provider selection,
credentials, metering, and billing belong to Relancify.

## End-to-end examples

The repository contains four real integration scenarios:

```bash
git clone https://github.com/NKSTUD/relancify-sdk.git
cd relancify-sdk

python3 -m venv .venv
.venv/bin/pip install -e .

export RELANCIFY_API_KEY="your-key"
export RELANCIFY_BASE_URL="https://api.relancify.com/api/v1"

.venv/bin/python -m examples.text.individual_agent
.venv/bin/python -m examples.text.multi_agent
.venv/bin/python -m examples.voice.individual_agent
.venv/bin/python -m examples.voice.multi_agent
```

The examples create real resources and consume workspace credits. They delete
created agents by default.

See the
[complete examples guide](https://github.com/NKSTUD/relancify-sdk/blob/main/examples/README.md)
for model selection, voice-provider configuration, cleanup behavior, and
production prerequisites.

## License and support

- Homepage: https://www.relancify.com
- Source: https://github.com/NKSTUD/relancify-sdk
- Issues: https://github.com/NKSTUD/relancify-sdk/issues
