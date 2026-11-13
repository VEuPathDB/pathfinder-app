from uuid import UUID


def format_uuid(value: UUID | None) -> str | None:
    return str(value) if value is not None else None
