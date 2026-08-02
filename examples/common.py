from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, NoReturn

from relancify_sdk import Relancify

DEFAULT_BASE_URL = "https://api.relancify.com/api/v1"
TERMINAL_OPERATION_STATUSES = {"ready", "failed"}


@dataclass(frozen=True)
class ExampleSettings:
    api_key: str
    base_url: str
    keep_resources: bool

    @classmethod
    def from_environment(cls) -> "ExampleSettings":
        api_key = os.getenv("RELANCIFY_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "RELANCIFY_API_KEY is required. Export it in your shell; "
                "never paste it into a source file."
            )

        return cls(
            api_key=api_key,
            base_url=os.getenv("RELANCIFY_BASE_URL", DEFAULT_BASE_URL).strip(),
            keep_resources=_environment_flag("RELANCIFY_KEEP_RESOURCES"),
        )


@dataclass(frozen=True)
class RuntimeProbe:
    session_id: str
    response: dict[str, Any]


def create_client(settings: ExampleSettings) -> Relancify:
    return Relancify(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=60.0,
    )


def select_text_model(
    client: Relancify,
    *,
    require_tool_calling: bool = False,
    require_structured_output: bool = False,
    environment_name: str = "RELANCIFY_TEXT_MODEL",
) -> str:
    configured_model = os.getenv(environment_name, "").strip()
    if configured_model:
        return configured_model

    response = client.models.list(page=1, page_size=100)
    items = response.get("items", []) if isinstance(response, dict) else []
    models = [item for item in items if isinstance(item, dict) and item.get("id")]

    if require_tool_calling:
        models = [
            item
            for item in models
            if item.get("capabilities", {}).get("tool_calling") is True
        ]
    if require_structured_output:
        models = [
            item
            for item in models
            if item.get("capabilities", {}).get("structured_output") is True
        ]

    if not models:
        requirements = []
        if require_tool_calling:
            requirements.append("tool calling")
        if require_structured_output:
            requirements.append("structured output")
        requirement = (
            f" with {' and '.join(requirements)} support" if requirements else ""
        )
        raise RuntimeError(
            f"No managed text model{requirement} is available for this workspace. "
            f"Set {environment_name} explicitly or configure the model catalog."
        )

    models.sort(
        key=lambda item: (
            not bool(item.get("recommended")),
            str(item.get("name") or item["id"]).lower(),
        )
    )
    return str(models[0]["id"])


def build_voice_agent_payload(
    client: Relancify,
    *,
    name: str,
    instructions: str,
    first_message: str,
) -> dict[str, Any]:
    voice = _select_voice(client)
    voice_id = str(voice["voice_id"])
    tts_model = _select_tts_model(voice)
    llm_model = os.getenv("RELANCIFY_VOICE_LLM_MODEL", "").strip() or select_text_model(
        client
    )
    stt_model = os.getenv(
        "RELANCIFY_VOICE_STT_MODEL",
        "gpt-4o-mini-transcribe",
    ).strip()

    language = os.getenv("RELANCIFY_VOICE_LANGUAGE", "fr").strip() or "fr"
    return {
        "name": name,
        "interaction_mode": "voice",
        "instructions": instructions,
        "status": "active",
        "rag_enabled": False,
        "llm_model": llm_model,
        "stt_model": stt_model,
        "tts_model": tts_model,
        "voice": voice_id,
        "language": language,
        "first_message": first_message,
        "session": {
            "allow_interruptions": True,
            "disable_first_message_interruptions": True,
            "max_duration_seconds": 300,
            "client_events": [
                "interruption",
                "user_transcript",
                "agent_response",
            ],
        },
        "temperature": 0.2,
        "runtime": {
            "livekit": {
                "room_prefix": "relancify-sdk-example",
                "session": {"preemptive_generation": True},
                "turn_handling": {
                    "endpointing": {
                        "mode": "fixed",
                        "min_delay": 0.5,
                        "max_delay": 3.0,
                    },
                    "interruption": {
                        "enabled": True,
                        "mode": "auto",
                        "min_duration": 0.5,
                        "min_words": 0,
                        "false_interruption_timeout": 2.0,
                        "resume_false_interruption": True,
                    },
                },
            }
        },
    }


def prepare_voice_agent(
    client: Relancify,
    agent: dict[str, Any],
    *,
    timeout_seconds: float = 90.0,
) -> None:
    del client, agent, timeout_seconds
    print("Agent prêt: le runtime LiveKit géré ne demande aucune publication.")


def wait_for_operation(
    client: Relancify,
    operation_id: str,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        operation = client.operations.get(operation_id)
        if operation.get("status") in TERMINAL_OPERATION_STATUSES:
            return operation
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Operation {operation_id} did not finish within {timeout_seconds:.0f}s."
            )
        time.sleep(1.0)


def open_runtime_probe(
    client: Relancify,
    agent_id: str,
) -> RuntimeProbe:
    response = client.runtime.create_session(agent_id)
    session_id = str(
        response.get("runtime_session_id") or response.get("session_id") or ""
    )
    if not session_id:
        raise RuntimeError("The runtime session response did not contain a session ID.")

    provider = str(response.get("provider") or "unknown")
    print(f"Session runtime active: {session_id} (provider={provider})")
    _print_connection_summary(response)

    if provider in {"openai", "elevenlabs"}:
        token_response = client.runtime.create_connect_token(session_id)
        relay_url = client.runtime.build_websocket_url(
            session_id,
            connect_token=str(token_response["connect_token"]),
        )
        print(f"Relais WebSocket validé: {relay_url.split('?', 1)[0]}")
        print(
            "Jeton de connexion éphémère reçu "
            f"(expiration={token_response.get('expires_at_unix')}); valeur masquée."
        )

    return RuntimeProbe(session_id=session_id, response=response)


def close_runtime_probe(
    client: Relancify,
    probe: RuntimeProbe | None,
) -> None:
    if probe is None:
        return
    try:
        client.runtime.close_session(probe.session_id)
        print(f"Session runtime fermée: {probe.session_id}")
    except Exception as exc:
        print(
            f"Warning: unable to close runtime session {probe.session_id}: {exc}",
            file=sys.stderr,
        )


def cleanup_agents(
    client: Relancify,
    agent_ids: list[str],
    *,
    keep_resources: bool,
) -> None:
    if keep_resources:
        print("Agents conservés: " + ", ".join(agent_ids))
        return

    for agent_id in reversed(agent_ids):
        try:
            client.agents.delete(agent_id)
            print(f"Agent supprimé: {agent_id}")
        except Exception as exc:
            print(f"Warning: unable to delete {agent_id}: {exc}", file=sys.stderr)


def run_example(main: Callable[[], None]) -> NoReturn:
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest interrompu.", file=sys.stderr)
        raise SystemExit(130) from None
    except Exception as exc:
        print(f"\nTest échoué: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    raise SystemExit(0)


def _environment_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _select_voice(client: Relancify) -> dict[str, Any]:
    voices = [voice for voice in client.voices.list() if isinstance(voice, dict)]
    configured_voice_id = os.getenv("RELANCIFY_VOICE_ID", "").strip()
    if configured_voice_id:
        for voice in voices:
            if str(voice.get("voice_id") or "") == configured_voice_id:
                return voice
        raise RuntimeError(
            "RELANCIFY_VOICE_ID is not present in the workspace voice catalog."
        )

    if voices:
        return voices[0]
    raise RuntimeError("No active voice is available in the workspace catalog.")


def _select_tts_model(voice: dict[str, Any]) -> str:
    configured_model = os.getenv("RELANCIFY_VOICE_TTS_MODEL", "").strip()
    if configured_model:
        return configured_model

    supported_models = voice.get("supported_tts_models")
    if isinstance(supported_models, list):
        ordered_models = sorted(
            (item for item in supported_models if isinstance(item, dict)),
            key=lambda item: not bool(item.get("is_default")),
        )
        for model in ordered_models:
            if model.get("model_key"):
                return str(model["model_key"])

    model = str(voice.get("tts_model_key") or "").strip()
    if model:
        return model
    raise RuntimeError(
        "The selected voice has no TTS model. Set RELANCIFY_VOICE_TTS_MODEL."
    )


def _print_connection_summary(response: dict[str, Any]) -> None:
    connection = (
        response.get("connection")
        if isinstance(response.get("connection"), dict)
        else {}
    )
    options = connection.get("options")
    if not isinstance(options, list) or not options:
        print("Aucune option de transport n'a été retournée.")
        return

    for option in options:
        if not isinstance(option, dict):
            continue
        auth = option.get("auth") if isinstance(option.get("auth"), dict) else {}
        print(
            "Transport disponible: "
            f"{option.get('transport')} "
            f"(url={option.get('url')}, auth={auth.get('type')}, token masqué)"
        )
