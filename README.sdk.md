# Relancify SDK (Python)

SDK Python pour consommer l'API Relancify.

## Installation

```bash
pip install relancify-sdk
```

## Usage rapide

```python
from relancify_sdk import RelancifyClient

client = RelancifyClient(
    base_url="https://api.relancify.com/api/v1",
    bearer="<access_token>",  # ou api_key="sk_..."
)

agents = client.agents.list()
print(len(agents))

client.close()
```

## Ressources disponibles

- `client.agents`
- `client.runtime`
- `client.users`
- `client.voices`
- `client.api_keys`

## Notes

- Le SDK utilise `httpx` en mode synchrone.
- Les erreurs HTTP remontent via `relancify_sdk.errors.ApiError`.
