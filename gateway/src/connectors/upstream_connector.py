import time

import requests

from errors import UpstreamUnavailable
from utils.logger import get_logger

# o que vem do outro serviço e volta para o app
PASS_BACK_HEADERS = ("content-type", "retry-after")


class UpstreamResponse:
    def __init__(self, status: int, body: bytes, headers: dict) -> None:
        self.status = status
        self.body = body
        self.headers = headers


class UpstreamConnector:
    # repassa a requisição como veio: corpo em bytes, sem reinterpretar o JSON
    def __init__(self, name: str, base_url: str, token: str, timeout: int) -> None:
        self.logger = get_logger(f"UpstreamConnector.{name}")
        self.base_url = base_url
        self.token = token
        self.timeout = timeout

    def forward(self, method: str, path: str, query: str, body: bytes, headers: dict) -> UpstreamResponse:
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        headers = dict(headers, **{"INTERNAL-TOKEN": self.token})
        started_at = time.perf_counter()
        try:
            response = requests.request(method, url, data=body or None, headers=headers, timeout=self.timeout)
        except requests.RequestException as error:
            self.logger.error(f"{method} {path} sem resposta: {error}")
            raise UpstreamUnavailable()

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        self.logger.info(f"{response.status_code} {method} {path} - {elapsed_ms:.1f} ms")
        back = {k: v for k, v in response.headers.items() if k.lower() in PASS_BACK_HEADERS}
        return UpstreamResponse(response.status_code, response.content, back)
