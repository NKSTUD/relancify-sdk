from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, NoReturn

from relancify_sdk import RelancifyClient


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


def create_client(settings: ExampleSettings) -> RelancifyClient:
    return RelancifyClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=60.0,
    )


def select_text_model(
    client: RelancifyClient,
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
            f" with {' and '.join(requirements)} support"
            if requirements
            else ""
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
    client: RelancifyClient,
    *,
    name: str,
    instructions: str,
    first_message: str,
) -> dict[str, Any]:
    runtime_provider = os.getenv(
        "RELANCIFY_VOICE_RUNTIME_PROVIDER",
        "livekit",
    ).strip().lower()
    if runtime_provider not in {"livekit", "openai", "elevenlabs"}:
        raise RuntimeError(
            "RELANCIFY_VOICE_RUNTIME_PROVIDER must be livekit, openai, or elevenlabs."
        )

    voice = _select_voice(client, runtime_provider=runtime_provider)
    voice_id = str(voice["voice_id"])
    tts_model = _select_tts_model(voice)
    tts_provider = _select_tts_provider(voice, voice_id)

    if runtime_provider == "openai":
        llm_model = os.getenv(
            "RELANCIFY_VOICE_LLM_MODEL",
            "gpt-realtime-mini",
        ).strip()
        llm_provider = "openai"
        stt_model = os.getenv(
            "RELANCIFY_VOICE_STT_MODEL",
            "gpt-4o-mini-transcribe",
        ).strip()
        stt_provider = "openai"
    elif runtime_provider == "elevenlabs":
        llm_model = (
            os.getenv("RELANCIFY_VOICE_LLM_MODEL", "").strip()
            or select_text_model(client)
        )
        llm_provider = "elevenlabs"
        stt_model = os.getenv(
            "RELANCIFY_VOICE_STT_MODEL",
            "scribe_realtime",
        ).strip()
        stt_provider = "elevenlabs"
    else:
        llm_model = (
            os.getenv("RELANCIFY_VOICE_LLM_MODEL", "").strip()
            or select_text_model(client)
        )
        llm_provider = os.getenv("RELANCIFY_VOICE_LLM_PROVIDER", "").strip() or None
        stt_model = os.getenv(
            "RELANCIFY_VOICE_STT_MODEL",
            "gpt-4o-mini-transcribe",
        ).strip()
        stt_provider = os.getenv(
            "RELANCIFY_VOICE_STT_PROVIDER",
            "openai",
        ).strip()

    language = os.getenv("RELANCIFY_VOICE_LANGUAGE", "fr").strip() or "fr"
    payload: dict[str, Any] = {
        "name": name,
        "status": "active",
        "modality": "voice",
        "primary_provider": runtime_provider,
        "prompt": {
            "system": instructions,
            "rag_enabled": False,
        },
        "session": {
            "first_message": first_message,
            "language": language,
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
            "model": llm_model,
            "temperature": 0.2,
        },
        "stt": {
            "provider": stt_provider,
            "model": stt_model,
            "language": language,
        },
        "tts": {
            "provider": tts_provider,
            "model": tts_model,
            "voice_id": voice_id,
            "language": language,
            "voice": {"speed": 1.0},
        },
        "tools": [],
        "runtime": {
            "provider": runtime_provider,
        },
    }
    if llm_provider:
        payload["llm"]["provider"] = llm_provider
    if runtime_provider == "livekit":
        payload["runtime"]["livekit"] = {
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

    return payload


def prepare_voice_agent(
    client: RelancifyClient,
    agent: dict[str, Any],
    *,
    timeout_seconds: float = 90.0,
) -> None:
    runtime = agent.get("runtime") if isinstance(agent.get("runtime"), dict) else {}
    runtime_provider = str(
        runtime.get("provider") or agent.get("primary_provider") or ""
    ).lower()
    if runtime_provider == "livekit":
        print("Publication provider: non requise pour le runtime LiveKit.")
        return

    accepted = client.agents.publish(str(agent["id"]))
    operation_id = str(accepted["operation_id"])
    operation = wait_for_operation(
        client,
        operation_id,
        timeout_seconds=timeout_seconds,
    )
    if operation.get("status") != "ready":
        detail = operation.get("error_detail") or "unknown provider error"
        raise RuntimeError(f"Voice agent publication failed: {detail}")
    print(f"Publication provider prête (operation={operation_id}).")


def wait_for_operation(
    client: RelancifyClient,
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
    client: RelancifyClient,
    agent_id: str,
) -> RuntimeProbe:
    response = client.agents.create_runtime_session(agent_id)
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
    client: RelancifyClient,
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
    client: RelancifyClient,
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


def _select_voice(
    client: RelancifyClient,
    *,
    runtime_provider: str,
) -> dict[str, Any]:
    voices = [voice for voice in client.voices.list() if isinstance(voice, dict)]
    configured_voice_id = os.getenv("RELANCIFY_VOICE_ID", "").strip()
    if configured_voice_id:
        for voice in voices:
            if str(voice.get("voice_id") or "") == configured_voice_id:
                return voice
        raise RuntimeError(
            "RELANCIFY_VOICE_ID is not present in the workspace voice catalog."
        )

    preferred_providers = (
        ["livekit", "elevenlabs", "openai"]
        if runtime_provider == "livekit"
        else [runtime_provider]
    )
    for provider in preferred_providers:
        for voice in voices:
            if str(voice.get("provider") or "").lower() == provider:
                return voice

    raise RuntimeError(
        f"No compatible voice is available for the {runtime_provider} runtime."
    )


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


def _select_tts_provider(voice: dict[str, Any], voice_id: str) -> str:
    configured_provider = os.getenv("RELANCIFY_VOICE_TTS_PROVIDER", "").strip()
    if configured_provider:
        return configured_provider

    descriptor_prefix = voice_id.partition(":")[0]
    if "/" in descriptor_prefix:
        return descriptor_prefix.partition("/")[0]

    provider = str(voice.get("provider") or "").strip().lower()
    if provider and provider != "livekit":
        return provider

    supported_models = voice.get("supported_tts_models")
    if isinstance(supported_models, list):
        for model in supported_models:
            if isinstance(model, dict) and model.get("provider"):
                return str(model["provider"])

    raise RuntimeError(
        "Unable to infer the voice TTS provider. "
        "Set RELANCIFY_VOICE_TTS_PROVIDER."
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
