from typing import Any, Dict, Optional
from urllib.parse import unquote
from uuid import UUID

from relancify_sdk.http import HttpClient


def _to_path_conversation_id(value: str) -> str:
    raw = str(value or "").strip()
    try:
        normalized = str(UUID(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid conversation_id. Expected UUID format.") from exc
    return normalized


def _extract_filename(content_disposition: str) -> Optional[str]:
    raw = str(content_disposition or "").strip()
    if not raw:
        return None

    for segment in [part.strip() for part in raw.split(";") if part.strip()]:
        lowered = segment.lower()
        if lowered.startswith("filename*="):
            encoded = segment.split("=", 1)[1].strip().strip('"')
            if "''" in encoded:
                encoded = encoded.split("''", 1)[1]
            decoded = unquote(encoded)
            cleaned = str(decoded or "").strip()
            if cleaned:
                return cleaned
        if lowered.startswith("filename="):
            decoded = segment.split("=", 1)[1].strip().strip('"')
            cleaned = str(decoded or "").strip()
            if cleaned:
                return cleaned
    return None


class ConversationsResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def get_audio(self, conversation_id: str) -> Dict[str, Any]:
        normalized_id = _to_path_conversation_id(conversation_id)
        response = self._client.request_response(
            "GET",
            f"/conversations/{normalized_id}/audio",
        )
        content_type = str(response.headers.get("content-type") or "").split(";")[0].strip()
        filename = _extract_filename(str(response.headers.get("content-disposition") or ""))
        payload = bytes(response.content or b"")
        return {
            "conversation_id": normalized_id,
            "audio_bytes": payload,
            "content_type": content_type or "application/octet-stream",
            "filename": filename,
            "byte_length": len(payload),
        }
