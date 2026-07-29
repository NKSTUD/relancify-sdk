# Code-first agents design

Status: implemented in SDK `0.8.0` against `openai-agents 0.19.1`.

## Goal

Relancify uses the OpenAI Agents SDK as the local orchestrator and provides the
model gateway, provider routing, credentials, usage tracking, and billing.

An agent may be:

- defined only in application code;
- explicitly saved in Relancify and referenced by its `ag_...` ID.

Saving an agent is optional. It is never an implicit side effect of creating an
`Agent` object.

## Public model selection

The developer passes a public Relancify model name directly to the native
`Agent`:

```python
agent = Agent(
    name="Support",
    instructions="Help customers with their orders.",
    model="support-fast",
)
```

The developer does not write `relancify.model(...)` and does not select a
provider. Relancify maps `support-fast` to the active provider route and
upstream model configured in its catalog.

## Synchronous client

```python
from agents import Agent
from relancify_sdk import RelancifyClient

client = RelancifyClient(api_key="rel_...")

agent = Agent(
    name="Support",
    instructions="Help customers with their orders.",
    model="support-fast",
)

result = client.invoke(agent, input="Where is my order?")
print(result.final_output)
```

## Asynchronous client

The async client exposes the same method names:

```python
from agents import Agent
from relancify_sdk import AsyncRelancifyClient

async with AsyncRelancifyClient(api_key="rel_...") as client:
    agent = Agent(
        name="Support",
        instructions="Help customers with their orders.",
        model="support-fast",
    )

    result = await client.invoke(agent, input="Where is my order?")
```

- `RelancifyClient` is synchronous.
- `AsyncRelancifyClient` is asynchronous.
- `invoke()` returns the final native Agents SDK result.
- `stream()` exposes native streaming events.

There are no `invoke_async()`, `run_text()`, or `run_local()` variants in the
new code-first interface. The older hosted methods remain available for
backward compatibility.

## Local tools

Tools may be implemented directly in the customer's application:

```python
from agents import Agent, function_tool

@function_tool
def find_order(order_id: str) -> str:
    """Read an order from the application's database."""
    return f"Order {order_id} is ready to ship."

agent = Agent(
    name="Order support",
    instructions="Use find_order when an order must be retrieved.",
    model="support-fast",
    tools=[find_order],
)

result = client.invoke(agent, input="Where is order ORD-42?")
```

The tool executes in the customer's process. Relancify receives its schema,
arguments, and result as required by the model loop, but never receives the
Python function source code.

Structured outputs, handoffs, guardrails, hooks, context, and sessions remain
native OpenAI Agents SDK features:

```python
from pydantic import BaseModel

class SupportAnswer(BaseModel):
    answer: str
    requires_human: bool

billing_agent = Agent(
    name="Billing",
    instructions="Handle billing requests.",
    model="reasoning",
    output_type=SupportAnswer,
)

triage_agent = Agent(
    name="Triage",
    instructions="Transfer billing requests to Billing.",
    model="support-fast",
    handoffs=[billing_agent],
)

result = client.invoke(triage_agent, input="I was charged twice.")
```

The transport follows the `openai-agents 0.19.1` model interface. Function
tools, custom tools, deferred loading, tool search, programmatic tool calling,
structured tool outputs, context management, and prompt-cache options are
compiled when supported by the selected model route. Runner-managed retries
stay local, usage collection is always enabled for billing, and
provider-specific `extra_*` overrides fail explicitly because they would bypass
Relancify routing.

## Registered agents

Registration saves configuration and versions in Relancify. It does not deploy
or host the customer's application code.

```python
registered = client.agents.create(
    name="Support",
    instructions="Help customers with their orders.",
    model="support-fast",
)
```

A registered agent is invoked directly by ID:

```python
result = client.invoke(
    registered["id"],
    input="Where is my order?",
    tools=[find_order],
)

for event in client.stream(
    registered["id"],
    input="Track order ORD-42.",
    tools=[find_order],
):
    handle(event)
```

`load()` is not required in the public workflow. The SDK resolves the agent ID,
retrieves its current definition, builds the native `Agent`, and caches that
definition internally for 30 seconds by default. Set `agent_cache_ttl=0` to
refresh before every invocation, or call `client.clear_agent_cache(agent_id)`
after an update performed outside the SDK. Calls to `client.agents.update()`,
`publish()`, and `delete()` invalidate the matching cache entry automatically.

Local tool implementations must still be supplied by the application.
Registered hosted HTTP tools continue to run through the older hosted agent
workflow; code-first `invoke()` does not download executable tool code.
Both `invoke()` and `stream()` retain the registered agent ID in Relancify
usage and billing records.

## Responsibilities

The customer application owns:

- the Agents SDK runner;
- local tool execution;
- application context and local sessions;
- application secrets and database access.

Relancify owns:

- authentication and authorization;
- the public model catalog;
- provider credentials and routing;
- capability validation;
- run usage, credits, and billing.

Every model call passes through Relancify for usage tracking, whether the agent
is registered or exists only in code.

## Modalities and files

Model capabilities declare real modalities such as `text`, `image`, `audio`,
and `video`. A file is an input container, not a modality. PDF, DOCX, CSV, and
similar formats are tracked separately as supported file types.

## Out of scope for this phase

- hosted deployment of customer agent code;
- automatic agent registration;
- mandatory `load()` calls;
- provider names or provider API keys in customer agent code;
- separate agent APIs based on `text` or `local` execution labels.
