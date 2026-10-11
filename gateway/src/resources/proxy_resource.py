from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool

from connectors import UpstreamConnector
from constants import (
    EVENTS_API_TIMEOUT,
    EVENTS_API_TOKEN,
    EVENTS_API_URL,
    PAYMENTS_API_TIMEOUT,
    PAYMENTS_API_TOKEN,
    PAYMENTS_API_URL,
    USERS_API_TIMEOUT,
    USERS_API_TOKEN,
    USERS_API_URL,
)
from controllers import AuthController
from errors import TooManyRequests
from resources.auth_resource import client_ip
from utils.rate_limit import limiter
from utils.request_context import NO_REQUEST_ID, get_request_id

UPSTREAMS = {
    "users": UpstreamConnector("users", USERS_API_URL, USERS_API_TOKEN, USERS_API_TIMEOUT),
    "events": UpstreamConnector("events", EVENTS_API_URL, EVENTS_API_TOKEN, EVENTS_API_TIMEOUT),
    "payments": UpstreamConnector("payments", PAYMENTS_API_URL, PAYMENTS_API_TOKEN, PAYMENTS_API_TIMEOUT),
}

# só estes cabeçalhos do app seguem adiante; X-User-* vindo de fora é descartado
FORWARDED_HEADERS = ("content-type", "accept", "x-pix-signature")


class ProxyResource:
    def __init__(self, upstream: str, needs_session: bool = True, limit: tuple[str, int, int] | None = None) -> None:
        self.upstream = UPSTREAMS[upstream]
        self.needs_session = needs_session
        self.limit = limit

    async def forward(self, request: Request) -> Response:
        body = await request.body()
        return await run_in_threadpool(self._forward, request, body)

    def _forward(self, request: Request, body: bytes) -> Response:
        if self.limit:
            name, limit, window = self.limit
            if not limiter.allow((name, client_ip(request)), limit, window):
                raise TooManyRequests()

        headers = {k: v for k, v in request.headers.items() if k.lower() in FORWARDED_HEADERS}
        if get_request_id() != NO_REQUEST_ID:
            headers["X-Request-ID"] = get_request_id()

        if self.needs_session:
            session = AuthController().authenticate(request.headers.get("AUTH-TOKEN"))
            headers["X-User-Id"] = str(session.user_id)
            headers["X-User-Type"] = session.user_type

        upstream = self.upstream.forward(request.method, request.url.path, request.url.query, body, headers)
        return Response(content=upstream.body, status_code=upstream.status, headers=upstream.headers)
