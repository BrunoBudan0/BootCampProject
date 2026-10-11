from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import UserController
from utils.schema_handler import SchemaHandler


class UserResource:
    @SchemaHandler.validate("post_internal_login.json")
    def on_post_internal_login(self, payload: dict) -> JSONResponse:
        controller = UserController()
        user_dto = controller.login(payload)

        return JSONResponse(content=jsonable_encoder(user_dto), status_code=http_status.HTTP_200_OK)

    def on_get_me(self) -> JSONResponse:
        controller = UserController()
        caller_dto = controller.get_caller()

        return JSONResponse(content=jsonable_encoder(caller_dto), status_code=http_status.HTTP_200_OK)

    def on_get_internal_company(self, company_id: str) -> JSONResponse:
        controller = UserController()
        company_dto = controller.get_company_names(company_id)

        return JSONResponse(content=jsonable_encoder(company_dto), status_code=http_status.HTTP_200_OK)