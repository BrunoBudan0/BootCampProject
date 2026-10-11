from fastapi import Body, Request, status
from fastapi.responses import JSONResponse

from controllers import OperationController
from utils.caller import get_caller, parse_uuid
from utils.schema_handler import SchemaHandler


class CredentialResource:
    @SchemaHandler.validate("block_credential.json")
    def on_put_block(self, request: Request, event_attendee_id: str, payload: dict = Body(...)) -> JSONResponse:
        user_id, user_type = get_caller(request)
        body = OperationController().set_blocked(
            user_id, user_type, parse_uuid(event_attendee_id, "id"), payload["blocked"]
        )
        return JSONResponse(content=body, status_code=status.HTTP_200_OK)
