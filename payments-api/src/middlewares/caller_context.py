import uuid

from fastapi import FastAPI, Request

from database import get_context

CALLER_ID_HEADER = "X-User-Id"
CALLER_TYPE_HEADER = "X-User-Type"


def register_caller_context_middleware(application: FastAPI) -> None:
    @application.middleware("http")
    async def load_caller_into_context(request: Request, call_next):
        context = get_context()
        context.caller_id = parse_caller_id(request.headers.get(CALLER_ID_HEADER))
        context.caller_type = request.headers.get(CALLER_TYPE_HEADER)

        return await call_next(request)


def parse_caller_id(raw_caller_id):
    if raw_caller_id is None:
        return None

    try:
        return uuid.UUID(raw_caller_id)
    except ValueError:
        return None
