from __future__ import annotations

from typing import Any

from examples.common import (
    build_voice_agent_payload,
    open_runtime_probe,
    select_text_model,
)


class _Models:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items

    def list(self, *, page: int, page_size: int) -> dict[str, Any]:
        return {"items": self._items, "page": page, "page_size": page_size}


class _Voices:
    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "voice_id": "elevenlabs/eleven_turbo_v2_5:voice-123",
                "name": "Test voice",
                "provider": "livekit",
                "tts_model_key": "eleven_turbo_v2_5",
                "supported_tts_models": [
                    {
                        "provider": "elevenlabs",
                        "model_key": "eleven_turbo_v2_5",
                        "is_default": True,
                    }
                ],
            }
        ]


class _CatalogClient:
    def __init__(self, models: list[dict[str, Any]]) -> None:
        self.models = _Models(models)
        self.voices = _Voices()


def _model(
    model_id: str,
    *,
    recommended: bool,
    tool_calling: bool = True,
    structured_output: bool = True,
) -> dict[str, Any]:
    return {
        "id": model_id,
        "name": model_id,
        "recommended": recommended,
        "capabilities": {
            "streaming": True,
            "tool_calling": tool_calling,
            "structured_output": structured_output,
        },
    }


def test_select_text_model_prefers_recommended_compatible_model(
    monkeypatch,
) -> None:
    monkeypatch.delenv("RELANCIFY_TEXT_MODEL", raising=False)
    client = _CatalogClient(
        [
            _model("recommended-without-tools", recommended=True, tool_calling=False),
            _model("compatible", recommended=False),
        ]
    )

    selected = select_text_model(
        client,  # type: ignore[arg-type]
        require_tool_calling=True,
    )

    assert selected == "compatible"


def test_build_voice_payload_uses_livekit_catalog_voice(monkeypatch) -> None:
    for name in (
        "RELANCIFY_TEXT_MODEL",
        "RELANCIFY_VOICE_ID",
        "RELANCIFY_VOICE_LLM_MODEL",
        "RELANCIFY_VOICE_LLM_PROVIDER",
        "RELANCIFY_VOICE_STT_MODEL",
        "RELANCIFY_VOICE_STT_PROVIDER",
        "RELANCIFY_VOICE_TTS_MODEL",
        "RELANCIFY_VOICE_TTS_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RELANCIFY_VOICE_RUNTIME_PROVIDER", "livekit")

    client = _CatalogClient([_model("managed-fast", recommended=True)])
    payload = build_voice_agent_payload(
        client,  # type: ignore[arg-type]
        name="Voice test",
        instructions="Answer briefly.",
        first_message="Hello.",
    )

    assert payload["primary_provider"] == "livekit"
    assert payload["llm"]["model"] == "managed-fast"
    assert payload["stt"]["provider"] == "openai"
    assert payload["tts"]["provider"] == "elevenlabs"
    assert payload["tts"]["voice_id"].endswith(":voice-123")
    assert payload["runtime"]["provider"] == "livekit"


class _RuntimeAgents:
    def create_runtime_session(self, agent_id: str) -> dict[str, Any]:
        return {
            "provider": "openai",
            "agent_id": agent_id,
            "runtime_session_id": "12345678-1234-1234-1234-123456789abc",
            "connection": {
                "options": [
                    {
                        "transport": "websocket",
                        "url": "wss://provider.example.test",
                        "auth": {
                            "type": "bearer",
                            "token": "provider-secret",
                        },
                    }
                ]
            },
        }


class _Runtime:
    def create_connect_token(self, session_id: str) -> dict[str, Any]:
        return {
            "connect_token": "runtime-secret",
            "expires_at_unix": 1234567890,
        }

    def build_websocket_url(
        self,
        session_id: str,
        *,
        connect_token: str,
    ) -> str:
        return (
            f"wss://api.example.test/runtime/sessions/{session_id}"
            f"?access_token={connect_token}"
        )


class _RuntimeClient:
    agents = _RuntimeAgents()
    runtime = _Runtime()


def test_runtime_probe_does_not_print_tokens(capsys) -> None:
    probe = open_runtime_probe(
        _RuntimeClient(),  # type: ignore[arg-type]
        "ag_12345678-1234-1234-1234-123456789abc",
    )

    output = capsys.readouterr().out
    assert probe.session_id == "12345678-1234-1234-1234-123456789abc"
    assert "provider-secret" not in output
    assert "runtime-secret" not in output
    assert "token masqué" in output
