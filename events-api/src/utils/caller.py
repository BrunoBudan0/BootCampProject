import uuid

from fastapi import Request

from errors import InvalidParameter


def get_caller(request: Request) -> tuple[uuid.UUID, str]:
    # quem chama vem do Gateway nesses dois headers
    user_id = request.headers.get("X-User-Id")
    user_type = request.headers.get("X-User-Type")

    if not user_id or not user_type:
        raise InvalidParameter("missing X-User-Id or X-User-Type")

    return parse_uuid(user_id, "X-User-Id"), user_type


def parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise InvalidParameter(f"{field} is not a valid uuid")
