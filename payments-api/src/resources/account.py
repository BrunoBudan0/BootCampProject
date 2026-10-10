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

    def on_get_list(self) -> JSONResponse:
        controller = AccountController()
        accounts_page = controller.list_accounts_for_caller()

        return JSONResponse(content=jsonable_encoder(accounts_page), status_code=http_status.HTTP_200_OK)

    @SchemaHandler.validate("put_internal_account_block.json")
    def on_put_internal_block(self, account_id: str, payload: dict) -> JSONResponse:
        controller = AccountController()
        account_dto = controller.set_account_blocked(account_id, payload["blocked"])

        return JSONResponse(content=jsonable_encoder(account_dto), status_code=http_status.HTTP_200_OK)

    def on_get_internal_event_reconciliation(self, event_id: str) -> JSONResponse:
        controller = AccountController()
        reconciliation = controller.reconcile_event(event_id)

        return JSONResponse(content=jsonable_encoder(reconciliation), status_code=http_status.HTTP_200_OK)