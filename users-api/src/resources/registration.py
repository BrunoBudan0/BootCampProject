from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import RegistrationController
from utils.schema_handler import SchemaHandler


class RegistrationResource:
    @SchemaHandler.validate("post_attendee.json")
    def on_post_attendee(self, payload: dict) -> JSONResponse:
        controller = RegistrationController()
        attendee_dto = controller.register_attendee(payload)

        return JSONResponse(content=jsonable_encoder(attendee_dto), status_code=http_status.HTTP_201_CREATED)

    @SchemaHandler.validate("post_organizer.json")
    def on_post_organizer(self, payload: dict) -> JSONResponse:
        controller = RegistrationController()
        organizer_dto = controller.register_organizer(payload)

        return JSONResponse(content=jsonable_encoder(organizer_dto), status_code=http_status.HTTP_201_CREATED)

    @SchemaHandler.validate("post_company.json")
    def on_post_company(self, payload: dict) -> JSONResponse:
        controller = RegistrationController()
        company_dto = controller.register_company(payload)

        return JSONResponse(content=jsonable_encoder(company_dto), status_code=http_status.HTTP_201_CREATED)