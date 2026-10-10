from dataclasses import dataclass, field

import requests

from connectors.rest_connector import BaseConnectorResponse, RestConnector
from constants import PAYMENTS_API_TIMEOUT, PAYMENTS_API_TOKEN, PAYMENTS_API_URL
from errors import UpstreamUnavailable


@dataclass
class TransferResult:
    # done: o dinheiro andou · refused: Pagamentos recusou e nada andou
    # unknown: não sabemos (timeout, 5xx) e pode ter andado
    outcome: str
    code: str | None = None
    status: int = 0
    transactions: list = field(default_factory=list)


class PaymentsConnector(RestConnector):
    def __init__(self) -> None:
        super().__init__(
            class_name=self.__class__.__name__,
            base_url=PAYMENTS_API_URL,
            timeout=PAYMENTS_API_TIMEOUT,
            internal_token=PAYMENTS_API_TOKEN,
        )

    def create_account(self, event_id, kind: str, idempotency_key: str, holder_id=None) -> str:
        payload = {
            "event_id": str(event_id),
            "kind": kind,
            "idempotency_key": idempotency_key,
        }
        # holder só em conta de usuário; fee e external não têm dono
        if holder_id is not None:
            payload["holder_id"] = str(holder_id)
        response = self._send("/internal/accounts", "POST", payload)

        # 201 = criou, 200 = já existia com essa chave
        if response.status not in (200, 201) or not response.json or "id" not in response.json:
            self.logger.error(f"create_account inesperado: {response.status} {response.json}")
            raise UpstreamUnavailable()

        return response.json["id"]

    def transfer(self, idempotency_key: str, payment_method: str, legs: list[tuple]) -> TransferResult:
        payload = {
            "idempotency_key": idempotency_key,
            "payment_method": payment_method,
            "transfers": [
                {
                    "source_account_id": str(source),
                    "destination_account_id": str(destination),
                    "amount_cents": amount,
                }
                for source, destination, amount in legs
            ],
        }
        return self._money("/internal/transactions", payload)

    def reverse(self, original_idempotency_key: str, idempotency_key: str) -> TransferResult:
        payload = {
            "original_idempotency_key": original_idempotency_key,
            "idempotency_key": idempotency_key,
        }
        return self._money("/internal/reversals", payload)

    def set_blocked(self, account_id, blocked: bool) -> None:
        response = self._send(f"/internal/accounts/{account_id}/block", "PUT", {"blocked": blocked})
        if response.status != 200:
            self.logger.error(f"bloqueio da conta {account_id} respondeu {response.status} {response.json}")
            raise UpstreamUnavailable()

    def reconciliation(self, event_id) -> dict:
        response = self._send(f"/internal/events/{event_id}/reconciliation", "GET")
        if response.status != 200 or not isinstance(response.json, dict):
            self.logger.error(f"conciliação do evento {event_id} respondeu {response.status}")
            raise UpstreamUnavailable()
        return response.json

    def _money(self, endpoint: str, payload: dict) -> TransferResult:
        key = payload["idempotency_key"]
        try:
            response = self.send(endpoint, "POST", payload)
        except requests.RequestException as error:
            self.logger.error(f"{endpoint} {key} sem resposta: {error}")
            return TransferResult("unknown")

        body = response.json if isinstance(response.json, dict) else {}
        if response.status in (200, 201):
            return TransferResult("done", status=response.status, transactions=body.get("transactions", []))
        if 400 <= response.status < 500:
            return TransferResult("refused", code=body.get("code"), status=response.status)

        self.logger.error(f"{endpoint} {key} respondeu {response.status}")
        return TransferResult("unknown", status=response.status)

    def _send(self, endpoint: str, method: str, payload: dict | None = None) -> BaseConnectorResponse:
        try:
            return self.send(endpoint, method, payload)
        except requests.RequestException as error:
            self.logger.error(f"{method} {endpoint} falhou: {error}")
            raise UpstreamUnavailable()
