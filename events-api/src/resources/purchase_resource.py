from fastapi import Body, Request, status
from fastapi.responses import JSONResponse

from controllers import PurchaseController
from utils.caller import get_caller, parse_uuid
from utils.schema_handler import SchemaHandler


class PurchaseResource:
    @SchemaHandler.validate("create_purchase.json")
    def on_post(self, request: Request, payload: dict = Body(...)) -> JSONResponse:
        user_id, user_type = get_caller(request)
        parse_uuid(payload["event_attendee_id"], "event_attendee_id")
        parse_uuid(payload["event_company_id"], "event_company_id")
        for item in payload["items"]:
            parse_uuid(item["product_id"], "product_id")

        body = PurchaseController().create_purchase(user_id, user_type, payload)
        return JSONResponse(content=body, status_code=status.HTTP_201_CREATED)