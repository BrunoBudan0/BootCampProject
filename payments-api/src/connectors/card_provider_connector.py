from connectors.rest_connector import BaseConnectorResponse, RestConnector
from constants import CARD_PROVIDER_URL, PROVIDERS_TIMEOUT


class CardProviderConnector(RestConnector):
    def __init__(self) -> None:
        super().__init__(
            class_name=__name__,
            base_url=CARD_PROVIDER_URL,
            timeout=PROVIDERS_TIMEOUT,
            internal_token=None,
        )

    def authorize(self, card_token: str, amount_cents: int, reference: str) -> BaseConnectorResponse:
        payload = {
            "card_token": card_token,
            "amount_cents": amount_cents,
            "reference": reference,
        }

        return self.send(endpoint="/authorizations", method="POST", payload=payload)
