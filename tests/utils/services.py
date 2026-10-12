"""Como os testes chegam até cada serviço.

Os testes são black-box (R1): falam com as APIs só por HTTP, pela mesma
porta que qualquer cliente usaria. Nada aqui importa código de src/: o
teste não sabe nem em que linguagem as APIs foram escritas.

Cada serviço vira um objeto com três coisas: onde ele atende, qual é o
token dele e um `send` que já põe esse token no header. Os valores
padrão são os mesmos do docker-compose.yml; se você mudou algo no .env,
o conftest.py já o carregou antes deste arquivo rodar.
"""

import os

import requests

# 127.0.0.1, e não localhost nem 0.0.0.0: as APIs internas publicam porta
# presa ao 127.0.0.1 (veja o docker-compose.yml), e no Windows o nome
# "localhost" pode ir primeiro para o endereço IPv6.
HOST = os.environ.get("TEST_HOST", "127.0.0.1")

# Quanto o teste espera por uma resposta antes de desistir. Teste sem
# prazo trava a suíte inteira no dia em que uma API para de responder.
TIMEOUT_SECONDS = 15

OFFLINE_MESSAGE = (
    "Não consegui falar com {name} em {base_url}.\n"
    "O sistema precisa estar de pé para os testes rodarem. Suba com:\n"
    "    docker compose up -d --build --wait"
)

# Marcador para "use o token do próprio serviço". Existe porque None já
# tem outro significado no `send`: não mandar token nenhum.
OWN_TOKEN = object()


class Service:
    def __init__(self, name, port_variable, default_port, token_variable, default_token):
        self.name = name
        self.base_url = f"http://{HOST}:{os.environ.get(port_variable, default_port)}"
        self.token = os.environ.get(token_variable, default_token)

    def send(self, method, path, json=None, headers=None, token=OWN_TOKEN, params=None, data=None):
        """Faz uma requisição a este serviço e devolve a resposta como veio.

        token=OWN_TOKEN (o padrão) manda o token do próprio serviço;
        token=None não manda nenhum; token="outro" manda esse valor.

        `params` vira a query string (?limit=10&page=0). `data` manda o
        corpo cru, byte a byte; é o que o teste do webhook Pix usa, porque
        a assinatura é calculada sobre os bytes exatos do corpo.
        """
        all_headers = dict(headers or {})

        if token is OWN_TOKEN:
            token = self.token

        if token is not None:
            all_headers["INTERNAL-TOKEN"] = token

        try:
            return requests.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                data=data,
                params=params,
                headers=all_headers,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.ConnectionError:
            raise RuntimeError(OFFLINE_MESSAGE.format(name=self.name, base_url=self.base_url)) from None

    def __repr__(self):
        return self.name


# No Gateway, o token é o do sistema cliente (app e painel).
gateway = Service("gateway", "GATEWAY_PORT", "3000", "CLIENT_INTERNAL_TOKEN", "client_default_token")
users = Service("users-api", "USERS_API_PORT", "3001", "USERS_API_TOKEN", "users_default_token")
events = Service("events-api", "EVENTS_API_PORT", "3002", "EVENTS_API_TOKEN", "events_default_token")
payments = Service("payments-api", "PAYMENTS_API_PORT", "3003", "PAYMENTS_API_TOKEN", "payments_default_token")

ALL_SERVICES = [gateway, users, events, payments]

# O Mockserver faz o papel dos provedores de cartão e Pix. Os testes combinam
# o que ele responde (expectation) e perguntam o que ele recebeu (verify).
MOCKSERVER_URL = f"http://{HOST}:{os.environ.get('MOCKSERVER_PORT', '1080')}"
