# Relancify SDK for Python

The Relancify Python SDK provides one API for registered hosted agents and
code-first agents orchestrated locally with the open-source Agents SDK. The
Agents SDK is used as a library: Relancify replaces its model provider and
disables its OpenAI tracing exporter for these runs.

Relancify handles authentication, model routing, hosted capabilities, runtime
provisioning, usage, and billing. For code-first agents, the agent loop and
local tools remain in your process.

## Requirements and installation

- Python 3.10 or newer
- a Relancify API key

```bash
pip install relancify-sdk
```

Keep API keys in environment variables rather than source code:

```bash
export RELANCIFY_API_KEY="rel_..."
```

## Clients

Use `Relancify` in synchronous code and `AsyncRelancify` in asynchronous code.
Both clients expose the same resources and method names.

```python
import os

from relancify_sdk import Relancify

client = Relancify(api_key=os.environ["RELANCIFY_API_KEY"])
models = client.models.list(page=1, page_size=50)
client.close()
```

```python
import os

from relancify_sdk import AsyncRelancify

client = AsyncRelancify(api_key=os.environ["RELANCIFY_API_KEY"])
models = await client.models.list(page=1, page_size=50)
await client.close()
```

Context managers remain available when they fit the application lifecycle:

```python
with Relancify(api_key="rel_...") as client:
    models = client.models.list()

async with AsyncRelancify(api_key="rel_...") as client:
    models = await client.models.list()
```

`RelancifyClient` and `AsyncRelancifyClient` remain compatibility aliases.

## Create a registered agent

Use `client.agents.create(...)` for both chat and voice agents. The public field
`interaction_mode` describes how a person interacts with the agent; it is not a
model modality.

### Chat

```python
agent = client.agents.create(
    name="Support",
    interaction_mode="chat",
    instructions="Help customers clearly.",
    model="support-fast",
    skills=[
        {
            "name": "Refund policy",
            "description": "Apply the refund rules consistently.",
            "instructions": "Verify the purchase date before offering a refund.",
        }
    ],
    capabilities=[
        "tool_12345678-1234-1234-1234-123456789abc",
        "intg_12345678-1234-1234-1234-123456789abc",
    ],
)
```

### Voice

```python
voice_agent = client.agents.create(
    name="French voice support",
    interaction_mode="voice",
    instructions="Help customers in French.",
    llm_model="support-fast",
    stt_model="speech-fr-realtime",
    tts_model="speech-natural-v2",
    voice="voice_fr_natural",
    language="fr",
    first_message="Bonjour, comment puis-je vous aider ?",
)
```

The developer chooses the exact public LLM, STT, TTS, and voice resources.
Relancify looks up their providers in its catalogs. Do not pass
`llm_provider`, `stt_provider`, `tts_provider`, or `runtime_provider` in the
standard API. Creation fails clearly when a selection is missing, inactive,
ambiguous, or incompatible.

LiveKit is the default managed voice runtime. Optional LiveKit behavior can be
configured without selecting a runtime provider:

```python
voice_agent = client.agents.create(
    name="Interruptible voice support",
    interaction_mode="voice",
    instructions="Answer briefly.",
    llm_model="support-fast",
    stt_model="speech-fr-realtime",
    tts_model="speech-natural-v2",
    voice="voice_fr_natural",
    language="fr",
    runtime={
        "livekit": {
            "session": {"preemptive_generation": True},
            "turn_handling": {
                "interruption": {"enabled": True, "mode": "auto"}
            },
        }
    },
)
```

## Run an agent

`client.run(agent_or_id, input)` is the only canonical non-streaming method.
Dispatch is based only on the target and the explicit `execution` option.

| Target | Default execution |
| --- | --- |
| Native `Agent` object | `local` |
| Registered `ag_...` ID | `hosted` |
| Registered ID with `execution="local"` | local |

### Registered hosted agent

```python
result = client.run(agent["id"], "Where is order ORD-42?")

print(result.output)
print(result.execution)       # hosted
print(result.conversation_id)
print(result.usage)
print(result.billing)
```

Continue a hosted conversation by passing the returned ID:

```python
second = client.run(
    agent["id"],
    "Summarize the previous answer.",
    conversation_id=result.conversation_id,
)
```

### Code-first local agent

```python
from relancify_sdk import Agent, Relancify, function_tool


@function_tool
def get_order_status(order_id: str) -> str:
    return f"Order {order_id} is ready."


support = Agent(
    name="Support",
    instructions="Use the order tool when needed.",
    model="support-fast",
    tools=[get_order_status],
)

client = Relancify(api_key="rel_...")
result = client.run(support, "Where is order ORD-42?")
print(result.output)
client.close()
```

The open-source Agents SDK runs the loop locally. Relancify supplies the model
gateway and billing boundary. Native handoffs, guardrails, structured outputs,
hooks, and sessions remain available. Relancify forces tracing off on this
runner path, including when a caller passes a `RunConfig`. The complete native
result is preserved as `result.raw`; `result.final_output` is a compatibility
alias for `result.output`.

Run a registered configuration locally only when that choice is explicit:

```python
result = client.run(
    agent["id"],
    "Check customer C-42.",
    execution="local",
    tools=[get_order_status],
)
```

Hosted capability IDs are not automatically executable Python tools. The SDK
therefore never infers local execution from the presence of `tools` or other
runner arguments.

## Stream an agent

`client.stream(agent_or_id, input)` works for hosted and local execution and
returns the same event envelope.

```python
stream = client.stream(agent["id"], "Explain the refund policy.")

for event in stream:
    if event.type == "output.delta":
        print(event.delta or "", end="")

print(stream.result.output)
```

```python
stream = client.stream(agent["id"], "Explain the refund policy.")

async for event in stream:
    if event.type == "output.delta":
        print(event.delta or "", end="")

print(stream.result.output)
```

Events expose `type`, `delta`, `data`, and `raw`. The shared vocabulary is:

- `run.started`
- `output.delta`
- `agent.changed`
- `tool.called`
- `tool.completed`
- `run.completed`
- `error`

Provider-specific or native Agents SDK details remain available through
`event.raw`.

## Skills, tools, MCP, and integrations

The execution method is unified, but hosted and local capability lifecycles
remain intentionally different.

### Hosted capabilities

Create an HTTP capability:

```python
order_tool = client.tools.create_http(
    name="Order status",
    url="https://api.example.com/orders/{order_id}",
    method="GET",
    input_schema={
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
        "additionalProperties": False,
    },
)
```

Register a remote MCP server:

```python
billing_mcp = client.tools.create_mcp_http(
    name="Billing MCP",
    server_url="https://mcp.example.com/",
    transport_type="streamable_http",
    headers={"Authorization": "Bearer secret"},
    allowed_tools=["get_invoice", "refund_invoice"],
)
```

Register a customer-owned stdio MCP definition:

```python
local_mcp_definition = client.tools.create_mcp_stdio(
    name="Internal files MCP",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/srv/docs"],
)
```

Site integrations use `intg_...` public IDs. Tools and registered MCP servers
use `tool_...` public IDs. Attach either kind through `capabilities`:

```python
agent = client.agents.create(
    name="Billing support",
    interaction_mode="chat",
    instructions="Use billing data when needed.",
    model="support-fast",
    capabilities=[billing_mcp["public_id"], stripe_connection["public_id"]],
)
```

Relancify resolves hosted credentials and executes hosted capabilities. Secrets
must never be placed in agent instructions or skill text.

### Local skills and MCP

Local skills are instruction bundles compiled into a native `Agent`. Local MCP
servers use the open-source Agents SDK objects and stay under the application's
lifecycle control.

```python
from relancify_sdk import (
    Agent,
    AsyncRelancify,
    MCPServerStreamableHttp,
    Skill,
    with_skills,
)

skill = Skill(
    name="Billing policy",
    description="Rules for invoice requests.",
    instructions="Verify the account before discussing invoices.",
)

async with MCPServerStreamableHttp(
    name="Billing MCP",
    params={"url": "https://mcp.example.com/"},
) as billing_mcp:
    agent = with_skills(
        Agent(
            name="Billing",
            instructions="Help with invoices.",
            model="support-fast",
            mcp_servers=[billing_mcp],
        ),
        [skill],
    )
    client = AsyncRelancify(api_key="rel_...")
    result = await client.run(agent, "Explain invoice INV-42.")
    await client.close()
```

Skills and MCP can be used together. They solve different problems: skills
guide behavior, while MCP exposes executable capabilities.

## Voice runtime sessions

Voice is a long-lived session, not a finite `run()` call. Its lifecycle belongs
to `client.runtime`:

```python
session = client.runtime.create_session(voice_agent["id"])
session_id = session["runtime_session_id"]

current = client.runtime.get_session(session_id)

# Connect the audio client using the returned transport information.

client.runtime.close_session(session_id)
```

The async client uses the same method names with `await`.

## Async parity

Only Python syntax changes between clients:

```python
from relancify_sdk import Agent, AsyncRelancify

client = AsyncRelancify(api_key="rel_...")
agent = Agent(
    name="Async support",
    instructions="Answer clearly.",
    model="support-fast",
)

result = await client.run(agent, "Say hello.")
stream = client.stream(agent, "Count to three.")
async for event in stream:
    print(event.type)

await client.close()
```

## Compatibility aliases

The following APIs remain temporarily available for migration:

- `RelancifyClient` and `AsyncRelancifyClient`
- `client.invoke(...)` for a native local result
- `client.agents.create_text(...)`
- `client.agents.run_text(...)` and `client.agents.stream_text(...)`
- `client.agents.create_runtime_session(...)`

New code should use `Relancify` / `AsyncRelancify`, `agents.create`,
`client.run`, `client.stream`, and `runtime.create_session`.

## Resource reference

| Resource | Main methods |
| --- | --- |
| `client.agents` | `list`, `get`, `create`, `update`, `delete`, `publish` |
| `client.models` | `list` |
| `client.voices` | `list` |
| `client.tools` | `list`, `get`, `create_http`, `create_mcp_http`, `create_mcp_stdio`, `update`, `delete` |
| `client.integrations` | `list_catalog`, Stripe connection methods |
| `client.runtime` | `create_session`, `get_session`, `close_session`, `create_connect_token`, `build_websocket_url` |
| `client.conversations` | `get_audio` |
| `client.operations` | `get` |
| `client.billing` | `summary`, `usage_ledger`, `credit_transactions` |
| `client.api_keys` | `list`, `create`, `revoke` |
| `client.users` | `me` |

## Error handling and security

```python
from relancify_sdk import ApiError

try:
    result = client.run(agent_id, "Hello")
except ApiError as exc:
    print(exc.status_code, exc.message, exc.retry_after_sec)
```

- Never commit Relancify or provider credentials.
- Use HTTPS outside local development.
- Treat MCP headers and integration tokens as secrets.
- Keep local MCP server processes scoped to the application lifecycle.
- Validate external tool input and output.
- Store `request_id` values when implementing idempotent retries.

## Examples

Runnable examples are available in [`examples`](examples):

- [`examples/text/individual_agent.py`](examples/text/individual_agent.py)
- [`examples/text/multi_agent.py`](examples/text/multi_agent.py)
- [`examples/voice/individual_agent.py`](examples/voice/individual_agent.py)
- [`examples/voice/multi_agent.py`](examples/voice/multi_agent.py)
- [`examples/realtime_voice_chat.py`](examples/realtime_voice_chat.py)

## License and support

See the project metadata for license terms. Report SDK issues through the
repository issue tracker.
