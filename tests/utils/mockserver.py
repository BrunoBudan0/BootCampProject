"""Conversa com o Mockserver, o ator no lugar dos provedores de cartão e Pix.

Três verbos, e só:
  expect    combina o roteiro: "quando chegar tal pedido, responda isto"
  received  pergunta se o pedido chegou, e quantas vezes
  reset     apaga os roteiros e tudo o que o ator recebeu

O Mockserver é um só para a suíte inteira. Todo teste que o programa
começa com reset(), para não herdar o roteiro de outro teste.

─────────────────────────────────────────────────────────────────────
O CONTRATO COM OS PROVEDORES (inventado por nós: está na RFC)
─────────────────────────────────────────────────────────────────────
Cartão   POST {CARD_PROVIDER_URL}/authorizations
         pedido:   {card_token, amount_cents, reference}
         resposta: 200 {status: "approved", authorization_id}
                   200 {status: "declined", reason}
Pix      POST {PIX_PROVIDER_URL}/charges
         pedido:   {amount_cents, reference}
         resposta: 201 {charge_id, copy_paste, expires_at}
`reference` é a chave de idempotência da recarga: é ela que permite
perguntar ao provedor, depois de um timeout, se a cobrança aconteceu.
"""

import json

import requests

from tests.utils.services import MOCKSERVER_URL

# Os caminhos, já com o prefixo de cada "provedor" (veja o
# docker-compose.yml: CARD_PROVIDER_URL e PIX_PROVIDER_URL).
CARD_AUTHORIZATIONS = "/card-provider/authorizations"
PIX_CHARGES = "/pix-provider/charges"

TIMEOUT_SECONDS = 15


def reset() -> None:
    requests.put(f"{MOCKSERVER_URL}/mockserver/reset", timeout=TIMEOUT_SECONDS).raise_for_status()


def expect(method: str, path: str, status_code: int, body: dict = None, delay_seconds: int = None) -> None:
    """Combina o roteiro: a todo `method path` que chegar, responda assim."""
    http_response = {"statusCode": status_code}

    if body is not None:
        http_response["headers"] = {"Content-Type": ["application/json"]}
        http_response["body"] = json.dumps(body)

    if delay_seconds is not None:
        http_response["delay"] = {"timeUnit": "SECONDS", "value": delay_seconds}

    expectation = {
        "httpRequest": {"method": method, "path": path},
        "httpResponse": http_response,
        "times": {"unlimited": True},
    }

    requests.put(
        f"{MOCKSERVER_URL}/mockserver/expectation", json=expectation, timeout=TIMEOUT_SECONDS
    ).raise_for_status()


def received(method: str, path: str, times: int, json_fields: dict = None) -> bool:
    """O ator recebeu exatamente `times` pedidos assim?

    `json_fields` restringe aos pedidos cujo corpo tem AO MENOS esses
    campos com esses valores (os outros campos do corpo não importam).
    """
    http_request = {"method": method, "path": path}

    if json_fields is not None:
        http_request["body"] = {
            "type": "JSON",
            "json": json.dumps(json_fields),
            "matchType": "ONLY_MATCHING_FIELDS",
        }

    verification = {"httpRequest": http_request, "times": {"atLeast": times, "atMost": times}}

    response = requests.put(f"{MOCKSERVER_URL}/mockserver/verify", json=verification, timeout=TIMEOUT_SECONDS)

    # 202: a verificação bateu. 406: não bateu (o corpo diz o que chegou).
    return response.status_code == 202
