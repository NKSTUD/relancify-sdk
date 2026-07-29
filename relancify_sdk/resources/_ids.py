from uuid import UUID


def normalize_uuid_path(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(str(value or "").strip()))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}. Expected UUID format.") from exc
