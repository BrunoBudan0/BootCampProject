import requests

from connectors.rest_connector import RestConnector
from constants import USERS_API_TIMEOUT, USERS_API_TOKEN, USERS_API_URL
from errors import InvalidCredentials, UpstreamUnavailable


class UsersConnector(RestConnector):
    def __init__(self) -> None:
        super().__init__(
            class_name=self.__class__.__name__,
            base_url=USERS_API_URL,
            timeout=USERS_API_TIMEOUT,
            internal_token=USERS_API_TOKEN,
        )

    def login(self, email: str, password: str, user_type: str) -> dict:
        payload = {"email": email, "password": password, "user_type": user_type}
        try:
            response = self.send("/internal/login", "POST", payload)
        except requests.RequestException as error:
            self.logger.error(f"login em Usuários falhou: {error}")
            raise UpstreamUnavailable()

        if response.status == 401:
            raise InvalidCredentials()
        body = response.json if isinstance(response.json, dict) else {}
        if response.status != 200 or "id" not in body or "user_type" not in body:
            self.logger.error(f"login em Usuários respondeu {response.status}")
            raise UpstreamUnavailable()
        return body
