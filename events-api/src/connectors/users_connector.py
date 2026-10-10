import requests

from connectors.rest_connector import RestConnector
from constants import USERS_API_TIMEOUT, USERS_API_TOKEN, USERS_API_URL
from errors import CompanyNotFound, UpstreamUnavailable


class UsersConnector(RestConnector):
    def __init__(self) -> None:
        super().__init__(
            class_name=self.__class__.__name__,
            base_url=USERS_API_URL,
            timeout=USERS_API_TIMEOUT,
            internal_token=USERS_API_TOKEN,
        )

    def ensure_company_exists(self, company_id) -> None:
        try:
            response = self.send(f"/internal/companies/{company_id}", "GET")
        except requests.RequestException as error:
            self.logger.error(f"GET /internal/companies falhou: {error}")
            raise UpstreamUnavailable()

        if response.status == 404:
            raise CompanyNotFound()
        if response.status != 200:
            self.logger.error(f"get company inesperado: {response.status} {response.json}")
            raise UpstreamUnavailable()