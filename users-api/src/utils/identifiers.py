import uuid


def parse_uuid_or_none(raw_value):
    try:
        return uuid.UUID(raw_value)
    except (TypeError, ValueError):
        return None
