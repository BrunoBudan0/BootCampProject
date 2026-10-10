from fastapi import Request
from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import TransactionController
from utils.schema_handler import SchemaHandler

DEFAULT_STATEMENT_LIMIT = 10
DEFAULT_STATEMENT_PAGE = 0


def created_or_replayed_status(created: bool) -> int:
    if created:
        return http_status.HTTP_201_CREATED

    return http_status.HTTP_200_OK


class TransactionResource:
    @SchemaHandler.validate("post_internal_transaction.json")
    def on_post_internal(self, payload: dict) -> JSONResponse:
        controller = TransactionController()
        batch_dto, created = controller.execute_internal_transactions(payload)

        return JSONResponse(content=jsonable_encoder(batch_dto), status_code=created_or_replayed_status(created))

    @SchemaHandler.validate("post_internal_reversal.json")
    def on_post_internal_reversal(self, payload: dict) -> JSONResponse:
        controller = TransactionController()
        batch_dto, created = controller.reverse_transactions(payload)

        return JSONResponse(content=jsonable_encoder(batch_dto), status_code=created_or_replayed_status(created))

    @SchemaHandler.validate("post_transfer.json")
    def on_post_transfer(self, payload: dict) -> JSONResponse:
        controller = TransactionController()
        transfer_dto, created = controller.transfer_for_caller(payload)

        return JSONResponse(content=jsonable_encoder(transfer_dto), status_code=created_or_replayed_status(created))

    def on_get_by_id(self, transaction_id: str) -> JSONResponse:
        controller = TransactionController()
        transaction_dto = controller.get_transaction_for_caller(transaction_id)

        return JSONResponse(content=jsonable_encoder(transaction_dto), status_code=http_status.HTTP_200_OK)

    @SchemaHandler.validate_query_params("get_account_statement.json")
    def on_get_statement(self, account_id: str, request: Request) -> JSONResponse:
        query_params = request.query_params
        limit = int(query_params.get("limit", DEFAULT_STATEMENT_LIMIT))
        page = int(query_params.get("page", DEFAULT_STATEMENT_PAGE))

        controller = TransactionController()
        statement = controller.statement_for_caller(
            account_id, limit, page, query_params.get("date_from"), query_params.get("date_to")
        )

        return JSONResponse(content=jsonable_encoder(statement), status_code=http_status.HTTP_200_OK)
