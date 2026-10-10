from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import AccountController
from utils.schema_handler import SchemaHandler


class AccountResource:
    @SchemaHandler.validate("post_internal_account.json")
    def on_post_internal(self, payload: dict) -> JSONResponse:
        controller = AccountController()
        account_dto, created = controller.create_account(payload)

        if created:
            status_code = http_status.HTTP_201_CREATED
        else:
            status_code = http_status.HTTP_200_OK

        return JSONResponse(content=jsonable_encoder(account_dto), status_code=status_code)

    def on_get_by_id(self, account_id: str) -> JSONResponse:
        controller = AccountController()
        account_dto = controller.get_account_for_caller(account_id)

        return JSONResponse(content=jsonable_encoder(account_dto), status_code=http_status.HTTP_200_OK)