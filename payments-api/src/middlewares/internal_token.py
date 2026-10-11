import hmac

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool

from constants import BYPASS_ENDPOINTS, INTERNAL_TOKEN
from errors.base_error import ForbiddenNotInternal
from errors.handlers import qi_exception_to_response
from models import CriticalLogPayment
from repositories import CriticalLogRepository

INTERNAL_ROUTES_PREFIX = "/internal/"


def internal_token_matches(received_token) -> bool:
    return hmac.compare_digest((received_token or "").encode("utf-8"), INTERNAL_TOKEN.encode("utf-8"))


def record_rejected_internal_call(route: str, refusal: ForbiddenNotInternal) -> None:
    CriticalLogRepository().record(
        CriticalLogPayment.INTERNAL_CALL_REJECTED,
        route=route,
        http_status=refusal.http_status,
        error_code=refusal.code,
    )


def register_internal_token_middleware(application: FastAPI) -> None:
    """Deixa passar só quem manda o header INTERNAL-TOKEN com o valor certo.

    O valor certo vem da variável de ambiente INTERNAL_TOKEN, nunca do
    código. As rotas de BYPASS_ENDPOINTS (raiz e health check) são públicas.

    Repare que aqui a gente DEVOLVE a resposta de erro em vez de levantar
    a exceção: dentro de um middleware, ninguém está escutando pra traduzir
    o erro — quem traduz são os exception handlers, que rodam mais pra
    dentro. Levantar aqui viraria um 500.
    """

    @application.middleware("http")
    async def check_internal_token(request: Request, call_next):
        is_public = request.url.path in BYPASS_ENDPOINTS

        if request.method == "OPTIONS" or is_public:
            return await call_next(request)

        if not internal_token_matches(request.headers.get("INTERNAL-TOKEN")):
            refusal = ForbiddenNotInternal()
            if request.url.path.startswith(INTERNAL_ROUTES_PREFIX):
                await run_in_threadpool(record_rejected_internal_call, request.url.path, refusal)
            return qi_exception_to_response(refusal)

        return await call_next(request)
