# Relancify SDK end-to-end examples

These examples exercise the public Python SDK against a real Relancify API:

- `text/individual_agent.py`: create a hosted text agent, run two conversation
  turns, verify real SSE streaming, then run the same registered agent through
  the local orchestration loop with `execution="local"`.
- `text/multi_agent.py`: define a local triage agent and two specialists, then
  verify a Relancify handoff through a managed model.
- `voice/individual_agent.py`: create a voice agent with the managed LiveKit
  runtime, create a runtime session, and validate its connection information.
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
.venv/bin/pip install "relancify-sdk==0.9.0"
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

The individual example deliberately exercises both execution locations:

- `client.run(agent_id, ...)` for a complete hosted turn;
- `client.stream(agent_id, ...)` for real incremental SSE deltas;
- `client.run(agent_id, ..., execution="local")` for a local orchestration loop.

## 4. Run voice scenarios

The managed runtime is LiveKit; no provider variable is required:

```bash
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

The scripts choose exact public LLM, STT, TTS, and voice resources. Relancify
resolves their providers from its catalogs; the examples never pass provider
names.

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
- provider credentials behind the selected catalog entries are configured;
- the deployed backend and installed SDK use compatible API contracts.
