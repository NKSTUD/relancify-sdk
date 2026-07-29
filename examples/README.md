# Relancify SDK end-to-end examples

These examples exercise the public Python SDK against a real Relancify API:

- `text/individual_agent.py`: create a hosted text agent, run two conversation
  turns, verify real SSE streaming, then invoke the same registered agent
  through the native Agents SDK loop.
- `text/multi_agent.py`: define a local triage agent and two specialists, then
  verify a native Agents SDK handoff through a managed Relancify model.
- `voice/individual_agent.py`: create a voice agent, publish it when required,
  create a runtime session, and validate its connection information.
- `voice/multi_agent.py`: create Sales and Support voice agents, classify the
  initial request with a structured routing agent, and open the selected
  agent's voice runtime session.

The examples consume workspace credits and create real resources. Agents are
deleted at the end by default. Runtime sessions are always closed.

## 1. Install the SDK

From the `relancify-sdk` directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

To test the published release instead:

```bash
python3 -m venv .venv
.venv/bin/pip install "relancify-sdk==0.8.0"
```

Keep the current repository as the working directory when running the modules
below, because the `examples` package is not included in the PyPI distribution.

## 2. Configure credentials

Never put a real key in Python code or commit it to Git. Export it only in the
current shell:

```bash
export RELANCIFY_API_KEY="your-key"
export RELANCIFY_BASE_URL="https://api.relancify.com/api/v1"
```

Create the key with these scopes:

- text examples: `agent:read` and `agent:write`;
- voice examples: `agent:read`, `agent:write`, and `voice:read`.

API key scopes cannot be inferred or elevated by the SDK. If the key is
missing a scope, create a new key from the Relancify developer page with the
required scopes.

For a local API:

```bash
export RELANCIFY_BASE_URL="http://localhost:8000/api/v1"
```

`environment.example` documents every optional override. Model and voice
catalog entries are selected automatically when an override is absent.

## 3. Run text scenarios

```bash
.venv/bin/python -m examples.text.individual_agent
.venv/bin/python -m examples.text.multi_agent
```

Pass a custom request to the multi-agent example:

```bash
.venv/bin/python -m examples.text.multi_agent \
  "L'application affiche une erreur au démarrage."
```

The individual example deliberately calls both hosted APIs:

- `client.agents.run_text(...)` for a complete hosted turn;
- `client.agents.stream_text(...)` for real incremental SSE deltas;
- `client.invoke(agent_id, ...)` for a native Agents SDK loop backed by the
  registered Relancify agent.

## 4. Run voice scenarios

The default runtime is LiveKit:

```bash
export RELANCIFY_VOICE_RUNTIME_PROVIDER="livekit"
.venv/bin/python -m examples.voice.individual_agent
.venv/bin/python -m examples.voice.multi_agent
```

Pass a custom request to the voice router:

```bash
.venv/bin/python -m examples.voice.multi_agent \
  "Je voudrais connaître le prix du forfait entreprise."
```

The voice scripts validate the SDK control plane through runtime connection
creation. They print transport URLs and authentication types but never print
session tokens. Capturing microphone audio and joining a LiveKit/WebRTC room
belongs in the web or mobile audio client and requires that transport's client
library.

For OpenAI or ElevenLabs direct runtimes, set
`RELANCIFY_VOICE_RUNTIME_PROVIDER` accordingly. The scripts then publish each
agent, wait for the publish operation to become `ready`, create a short-lived
runtime connect token, and validate the backend WebSocket relay URL.

The multi-agent voice example performs pre-call routing:

```text
Initial request -> structured routing agent -> Sales voice agent
                                           -> Support voice agent
```

It does not claim to transfer an already-open audio call. Mid-call transfers
need a runtime handoff tool supported and configured for the selected voice
provider.

## Keep created agents for inspection

By default, every created agent is deleted in a `finally` block. To inspect the
resources later in the Relancify dashboard:

```bash
export RELANCIFY_KEEP_RESOURCES="true"
```

Remember to delete those test agents manually when finished.

## Production configuration checklist

If a script fails at runtime, verify:

- the API key is active and belongs to the intended workspace;
- the workspace has credits and active text-model pricing entries;
- at least one managed text model and one compatible voice are active;
- LiveKit credentials and its worker are deployed for the LiveKit runtime;
- OpenAI or ElevenLabs provider credentials are present when selecting those
  direct runtimes;
- the deployed backend and installed SDK use compatible API contracts.
