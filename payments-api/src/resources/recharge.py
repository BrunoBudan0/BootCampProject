from fastapi import Request, Response
from fastapi import status as http_status
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import RechargeController
from resources.transaction import created_or_replayed_status
from utils.schema_handler import SchemaHandler

PIX_SIGNATURE_HEADER = "X-Pix-Signature"


class RechargeResource:
    @SchemaHandler.validate("post_recharge.json")
    def on_post(self, payload: dict) -> JSONResponse:
        controller = RechargeController()
        recharge_dto, created = controller.recharge_for_caller(payload)

        return JSONResponse(content=jsonable_encoder(recharge_dto), status_code=created_or_replayed_status(created))

    async def on_put_pix_webhook(self, transaction_id: str, request: Request) -> Response:
        raw_body = await request.body()
        signature = request.headers.get(PIX_SIGNATURE_HEADER)

        await run_in_threadpool(self._handle_pix_webhook, transaction_id, raw_body, signature)

        return Response(status_code=http_status.HTTP_204_NO_CONTENT)

    def _handle_pix_webhook(self, transaction_id: str, raw_body: bytes, signature) -> None:
        controller = RechargeController()
        controller.handle_pix_webhook(transaction_id, raw_body, signature)
