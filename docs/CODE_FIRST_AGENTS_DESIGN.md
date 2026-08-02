# Code-first agents architecture

Status: implemented architecture reference.

## Boundary

Relancify uses the open-source Agents SDK as its local orchestration engine.
The SDK is not a hosting service and does not move a customer's code-defined
agent into Relancify. Relancify supplies its own model provider and disables
the Agents SDK tracing exporter on its runner path, so using the orchestration
library does not send traces to an OpenAI service.

For a native `Agent` object:

1. the Agents SDK runner executes in the customer's Python process;
2. Python tools, handoffs, guardrails, hooks, sessions, skills, and local MCP
   servers remain local;
3. model requests pass through the Relancify model adapter;
4. Relancify resolves the public model, applies credentials, records usage, and
   bills the workspace.

For a registered `ag_...` ID, the default execution is hosted. Relancify loads
the stored prompt, models, skills, tools, MCP servers, and integrations and
executes the turn on its managed runtime.

## Unified invocation

```python
from relancify_sdk import Agent, Relancify

client = Relancify(api_key="rel_...")

local_agent = Agent(
    name="Support",
    instructions="Answer clearly.",
    model="support-fast",
)

local = client.run(local_agent, "Where is my order?")
hosted = client.run("ag_12345678-1234-1234-1234-123456789abc", "Hello")
```

Dispatch is deterministic:

- native `Agent` object: local;
- registered ID: hosted;
- registered ID with `execution="local"`: local.

Local execution is never inferred from optional runner arguments.

The asynchronous client has the same API:

```python
from relancify_sdk import AsyncRelancify

client = AsyncRelancify(api_key="rel_...")
result = await client.run(local_agent, "Where is my order?")
await client.close()
```

## Results and streams

Both execution modes return `AgentRunResult` with:

- `output`;
- `execution`;
- `conversation_id`;
- `usage`;
- `billing`;
- `raw`.

`raw` is the hosted response or native Agents SDK result. It is the escape
hatch for behavior not represented by the common envelope.

`client.stream(...)` returns normalized events for hosted and local runs. Each
event exposes `type`, `delta`, `data`, and `raw`. The common event vocabulary is
`run.started`, `output.delta`, `agent.changed`, `tool.called`,
`tool.completed`, `run.completed`, and `error`.

## Registered agent loaded locally

```python
result = client.run(
    "ag_12345678-1234-1234-1234-123456789abc",
    "Check order ORD-42.",
    execution="local",
    tools=[find_order],
)
```

Relancify loads and caches the registered agent definition, then builds a
native `Agent` backed by the registered agent's billing route. Hosted capability
IDs are declarative references and are not downloaded as executable Python.
The caller must provide local Python tools and local MCP server objects.

## Skills and MCP

Skills and MCP are supported together:

- a skill is an instruction bundle that guides behavior;
- an MCP server exposes executable capabilities.

Hosted skills and capability references are persisted with the registered
agent. Local skills are compiled through `with_skills()`, and local MCP server
objects follow the Agents SDK lifecycle in the customer's process.

## Model modalities

Agent interaction mode and model modalities are separate concepts. A chat
agent may use a model that accepts images, and a voice agent may use either a
native audio model or an STT → LLM → TTS pipeline.

- `interaction_mode`: `chat` or `voice`;
- `execution`: `hosted` or `local`;
- model capabilities: input/output modalities such as text, image, and audio.

Files are input containers, not modalities. Parsing and provider support for a
file type are separate capabilities.

## Compatibility

`invoke()` remains available for callers that need the native local Agents SDK
result directly. New code should use `run()` and access the same native object
through `result.raw` when necessary.
