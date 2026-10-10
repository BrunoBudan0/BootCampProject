from fastapi import Body, Request, status
from fastapi.responses import JSONResponse

from controllers import EventController, ParticipantController
from utils.caller import get_caller, parse_uuid
from utils.schema_handler import SchemaHandler


class EventResource:
    @SchemaHandler.validate("create_event.json")
    def on_post(self, request: Request, payload: dict = Body(...)) -> JSONResponse:
        user_id, user_type = get_caller(request)
        body = EventController().create_event(user_id, user_type, payload)
        return JSONResponse(content=body, status_code=status.HTTP_201_CREATED)

    @SchemaHandler.validate_query_params("list_query.json")
    def on_get_list(self, request: Request) -> JSONResponse:
        get_caller(request)
        limit = int(request.query_params.get("limit", 20))
        page = int(request.query_params.get("page", 1))
        body = EventController().list_events(limit, page)
        return JSONResponse(content=body, status_code=status.HTTP_200_OK)

    def on_get(self, request: Request, event_id: str) -> JSONResponse:
        get_caller(request)
        body = EventController().get_event(parse_uuid(event_id, "id"))
        return JSONResponse(content=body, status_code=status.HTTP_200_OK)

    @SchemaHandler.validate("add_company.json")
    def on_post_company(self, request: Request, event_id: str, payload: dict = Body(...)) -> JSONResponse:
        user_id, user_type = get_caller(request)
        parse_uuid(payload["company_id"], "company_id")
        body = ParticipantController().add_company(
            user_id, user_type, parse_uuid(event_id, "id"), payload
        )
        return JSONResponse(content=body, status_code=status.HTTP_201_CREATED)

    def on_post_attendee(self, request: Request, event_id: str) -> JSONResponse:
        user_id, user_type = get_caller(request)
        body = ParticipantController().add_attendee(user_id, user_type, parse_uuid(event_id, "id"))
        return JSONResponse(content=body, status_code=status.HTTP_201_CREATED)