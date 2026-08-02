# Relancify SDK examples

These examples create real agents and call the Relancify API.

## Install

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Set your credentials:

```bash
export RELANCIFY_API_KEY="rel_..."
export RELANCIFY_BASE_URL="https://api.relancify.com/api/v1"
```

The API key needs `agent:read` and `agent:write`. Voice examples also need
`voice:read`.

## Chat examples

```bash
.venv/bin/python -m examples.text.individual_agent
.venv/bin/python -m examples.text.multi_agent
```

The individual example creates a chat agent, continues a conversation,
streams a response, and runs the registered agent locally.

Pass a custom request to the multi-agent example:

```bash
.venv/bin/python -m examples.text.multi_agent \
  "L'application affiche une erreur au démarrage."
```

## Voice examples

```bash
.venv/bin/python -m examples.voice.individual_agent
.venv/bin/python -m examples.voice.multi_agent
```

The voice examples create agents and runtime sessions, then print the
connection information needed by an audio client. They use active models and
voices returned by the Relancify catalog.

Pass a custom request to the multi-agent voice example:

```bash
.venv/bin/python -m examples.voice.multi_agent \
  "Je voudrais connaître le prix du forfait entreprise."
```

## Keep created agents

Examples delete the agents they create. Keep them for inspection with:

```bash
export RELANCIFY_KEEP_RESOURCES="true"
```

Delete retained test agents from the dashboard when you finish.
