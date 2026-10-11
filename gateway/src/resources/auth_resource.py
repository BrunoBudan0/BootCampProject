from fastapi import Body, Request, status
from fastapi.responses import JSONResponse

from constants import LOGIN_PER_EMAIL, LOGIN_PER_IP
from controllers import AuthController
from errors import TooManyRequests
from utils.rate_limit import limiter
from utils.schema_handler import SchemaHandler


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


class AuthResource:
    @SchemaHandler.validate("login.json")
    def on_post_login(self, request: Request, payload: dict = Body(...)) -> JSONResponse:
        email = payload["email"].lower()
        if not limiter.allow(("login-ip", client_ip(request)), *LOGIN_PER_IP):
            raise TooManyRequests()
        if not limiter.allow(("login-email", email), *LOGIN_PER_EMAIL):
            raise TooManyRequests()

        body = AuthController().login(payload)
        return JSONResponse(content=body, status_code=status.HTTP_200_OK)
