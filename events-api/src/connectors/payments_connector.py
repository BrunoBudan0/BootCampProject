import requests

from connectors.rest_connector import RestConnector
from constants import PAYMENTS_API_TIMEOUT, PAYMENTS_API_TOKEN, PAYMENTS_API_URL
from errors import UpstreamUnavailable


class PaymentsConnector(RestConnector):
    def __init__(self) -> None:
        super().__init__(
            class_name=self.__class__.__name__,
            base_url=PAYMENTS_API_URL,
            timeout=PAYMENTS_API_TIMEOUT,
            internal_token=PAYMENTS_API_TOKEN,
        )

    def create_account(self, event_id, holder_id, kind: str, idempotency_key: str) -> str:
        payload = {
            "event_id": str(event_id),
            "holder_id": str(holder_id),
            "kind": kind,
            "idempotency_key": idempotency_key,
        }
        response = self._send("/internal/accounts", "POST", payload)

        if response.status not in (200, 201) or not response.json or "id" not in response.json:
            self.logger.error(f"create_account inesperado: {response.status} {response.json}")
            raise UpstreamUnavailable()

        return response.json["id"]

    def _send(self, endpoint: str, method: str, payload: dict = None):
        try:
            return self.send(endpoint, method, payload)
        except requests.RequestException as error:
            self.logger.error(f"{method} {endpoint} falhou: {error}")
            raise UpstreamUnavailable()