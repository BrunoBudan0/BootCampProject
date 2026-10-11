from connectors.rest_connector import BaseConnectorResponse, RestConnector
from constants import PIX_PROVIDER_URL, PROVIDERS_TIMEOUT


class PixProviderConnector(RestConnector):
    def __init__(self) -> None:
        super().__init__(
            class_name=__name__,
            base_url=PIX_PROVIDER_URL,
            timeout=PROVIDERS_TIMEOUT,
            internal_token=None,
        )

    def create_charge(self, amount_cents: int, reference: str) -> BaseConnectorResponse:
        payload = {
            "amount_cents": amount_cents,
            "reference": reference,
        }

        return self.send(endpoint="/charges", method="POST", payload=payload)
