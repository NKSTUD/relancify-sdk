# Relancify SDK for Python

Create and run chat or voice agents with one Python interface.

## Install

Relancify requires Python 3.10 or newer.

```bash
pip install relancify-sdk
export RELANCIFY_API_KEY="rel_..."
```

## Quick start

```python
import os

from relancify_sdk import Relancify

client = Relancify(api_key=os.environ["RELANCIFY_API_KEY"])

agent = client.agents.create(
    name="Customer support",
    interaction_mode="chat",
    instructions="Answer customer questions clearly and concisely.",
    model="gpt-4o-mini",
    status="active",
)

result = client.run(agent["id"], "Where is my order?")
print(result.output)

client.close()
```

Use `Relancify` in synchronous applications and `AsyncRelancify` in
asynchronous applications. Their resources and method names are the same.

## Choose models and voices

List the choices available to your workspace:

```python
models = client.models.list(page=1, page_size=100)
for model in models["items"]:
    print(model["id"], model["name"])

voices = client.voices.list()
for voice in voices:
    print(voice["voice_id"], voice["name"])
```

The examples below use these real catalog entries:

| Purpose | ID |
| --- | --- |
| Language model | `gpt-4o-mini` |
| Speech recognition | `gpt-4o-mini-transcribe` |
| Speech synthesis | `gpt-4o-mini-tts` |
| Voice | `alloy` |

## Create agents

Use `client.agents.create(...)` for both chat and voice agents.

### Chat agent

```python
agent = client.agents.create(
    name="Customer support",
    interaction_mode="chat",
    instructions="Answer customer questions in French.",
    model="gpt-4o-mini",
    status="active",
)
```

### Voice agent

```python
voice_agent = client.agents.create(
    name="French voice support",
    interaction_mode="voice",
    instructions="Answer customer questions in French with short sentences.",
    llm_model="gpt-4o-mini",
    stt_model="gpt-4o-mini-transcribe",
    tts_model="gpt-4o-mini-tts",
    voice="alloy",
    language="fr",
    first_message="Bonjour, comment puis-je vous aider ?",
    status="active",
)
```

### Creation parameters

| Parameter | Use |
| --- | --- |
| `name` | Name shown in Relancify |
| `interaction_mode` | `"chat"` or `"voice"` |
| `instructions` | The agent's role and rules |
| `model` | Language model for a chat agent |
| `llm_model` | Language model for a voice agent |
| `stt_model` | Speech recognition model for a voice agent |
| `tts_model` | Speech synthesis model for a voice agent |
| `voice` | Voice ID returned by `client.voices.list()` |
| `language` | Session language, such as `"fr"` or `"en"` |
| `first_message` | First sentence spoken by a voice agent |
| `skills` | Reusable instructions for the agent |
| `capabilities` | IDs of tools, MCP servers, or connected integrations |
| `status` | `"draft"`, `"active"`, or `"disabled"` |

## Run an agent

Use `client.run(agent_or_id, input)` for chat agents.

### Registered agent

```python
result = client.run(agent["id"], "Where is order ORD-42?")

print(result.output)
print(result.conversation_id)
print(result.usage)
print(result.billing)
```

Continue the same conversation with its returned ID:

```python
next_result = client.run(
    agent["id"],
    "Summarize your previous answer.",
    conversation_id=result.conversation_id,
)
```

### Code-first agent

Pass an `Agent` object to the same `client.run(...)` method:

```python
from relancify_sdk import Agent, Relancify, function_tool


@function_tool
def get_order_status(order_id: str) -> str:
    return f"Order {order_id} is ready."


support_agent = Agent(
    name="Support",
    instructions="Use the order tool when the customer asks about an order.",
    model="gpt-4o-mini",
    tools=[get_order_status],
)

client = Relancify(api_key="rel_...")
result = client.run(support_agent, "Where is order ORD-42?")
print(result.output)
client.close()
```

An `Agent` object runs in your application. An `ag_...` ID runs the registered
agent. To run a registered configuration in your application, set
`execution="local"`:

```python
result = client.run(
    agent["id"],
    "Check order ORD-42.",
    execution="local",
    tools=[get_order_status],
)
```

## Stream responses

`client.stream(...)` works with registered and code-first agents.

```python
stream = client.stream(agent["id"], "Explain the refund policy.")

for event in stream:
    if event.type == "output.delta":
        print(event.delta or "", end="")

print(stream.result.output)
```

Events use these types:

- `run.started`
- `output.delta`
- `agent.changed`
- `tool.called`
- `tool.completed`
- `run.completed`
- `error`

Each event exposes `type`, `delta`, `data`, and `raw`.

## Add skills

### Registered agent

Pass skills while creating the agent:

```python
from relancify_sdk import Skill

refund_policy = Skill(
    name="Refund policy",
    description="Rules for refund requests.",
    instructions="Check the purchase date before approving a refund.",
)

agent = client.agents.create(
    name="Refund support",
    interaction_mode="chat",
    instructions="Help customers with refund requests.",
    model="gpt-4o-mini",
    skills=[refund_policy],
    status="active",
)
```

### Code-first agent

Use `with_skills(...)` to add skills to an `Agent` object:

```python
from relancify_sdk import Agent, Skill, with_skills

refund_policy = Skill(
    name="Refund policy",
    instructions="Check the purchase date before approving a refund.",
)

agent = with_skills(
    Agent(
        name="Refund support",
        instructions="Help customers with refunds.",
        model="gpt-4o-mini",
    ),
    [refund_policy],
)
```

Load a Markdown skill from `SKILL.md` with `load_skill(...)`:

```python
from relancify_sdk import load_skill

refund_policy = load_skill("./skills/refunds")
```

## Add MCP servers and integrations

### Registered agent

Register a remote MCP server, then attach its ID to the agent:

```python
import os

billing_mcp = client.tools.create_mcp_http(
    name="Billing MCP",
    server_url="https://mcp.example.com/",
    transport_type="streamable_http",
    headers={
        "Authorization": f"Bearer {os.environ['BILLING_MCP_TOKEN']}"
    },
    allowed_tools=["get_invoice", "refund_invoice"],
)

agent = client.agents.create(
    name="Billing support",
    interaction_mode="chat",
    instructions="Help customers with invoices.",
    model="gpt-4o-mini",
    capabilities=[billing_mcp["public_id"]],
    status="active",
)
```

For a stdio MCP server:

```python
files_mcp = client.tools.create_mcp_stdio(
    name="Company documents",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/srv/docs"],
)
```

Attach an integration already connected in Relancify by adding its `intg_...`
ID to `capabilities`.

### Code-first agent

Pass an MCP server object to the `Agent`:

```python
from relancify_sdk import (
    Agent,
    AsyncRelancify,
    MCPServerStreamableHttp,
    Skill,
    with_skills,
)

client = AsyncRelancify(api_key="rel_...")
billing_policy = Skill(
    name="Billing policy",
    instructions="Verify the account before discussing an invoice.",
)

async with MCPServerStreamableHttp(
    name="Billing MCP",
    params={"url": "https://mcp.example.com/"},
) as billing_mcp:
    agent = with_skills(
        Agent(
            name="Billing support",
            instructions="Help customers with invoices.",
            model="gpt-4o-mini",
            mcp_servers=[billing_mcp],
        ),
        [billing_policy],
    )
    result = await client.run(agent, "Explain invoice INV-42.")
    print(result.output)

await client.close()
```

This example applies a skill and an MCP server to the same agent.

## Start a voice session

Voice agents use runtime sessions:

```python
session = client.runtime.create_session(voice_agent["id"])
session_id = session["runtime_session_id"]

current_session = client.runtime.get_session(session_id)
connect_token = client.runtime.create_connect_token(session_id)

client.runtime.close_session(session_id)
```

Use the returned session connection information and token in your audio client.

## Async client

Import `AsyncRelancify`, keep the same method names, and await network calls:

```python
import os

from relancify_sdk import Agent, AsyncRelancify

client = AsyncRelancify(api_key=os.environ["RELANCIFY_API_KEY"])

agent = Agent(
    name="Async support",
    instructions="Answer clearly.",
    model="gpt-4o-mini",
)

result = await client.run(agent, "Say hello.")
print(result.output)

stream = client.stream(agent, "Count to three.")
async for event in stream:
    if event.type == "output.delta":
        print(event.delta or "", end="")

await client.close()
```

Both clients can also be used as context managers.

## Result and errors

`client.run(...)` returns an `AgentRunResult` with:

- `output`
- `execution`
- `conversation_id`
- `usage`
- `billing`
- `raw`

Handle API errors with `ApiError`:

```python
from relancify_sdk import ApiError

try:
    result = client.run(agent["id"], "Hello")
except ApiError as error:
    print(error.status_code, error.message)
```

## Resources

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

## Examples

See the [complete examples](https://github.com/NKSTUD/relancify-sdk/tree/main/examples):

- [Chat agent](https://github.com/NKSTUD/relancify-sdk/blob/main/examples/text/individual_agent.py)
- [Multi-agent chat](https://github.com/NKSTUD/relancify-sdk/blob/main/examples/text/multi_agent.py)
- [Voice agent](https://github.com/NKSTUD/relancify-sdk/blob/main/examples/voice/individual_agent.py)
- [Multi-agent voice](https://github.com/NKSTUD/relancify-sdk/blob/main/examples/voice/multi_agent.py)

## Support

Report SDK issues in the [GitHub issue tracker](https://github.com/NKSTUD/relancify-sdk/issues).
