"""Ajudantes dos testes da API de Pagamentos.

Cada teste monta o próprio mundo PELA PORTA DA FRENTE (R1): conta nasce
por POST /internal/accounts e dinheiro entra por POST /internal/transactions
(da conta external do evento para a conta, método cash — exatamente o que
a recarga em dinheiro faz). Nenhum INSERT, nenhuma leitura de banco.

Cada teste também nasce num evento NOVO (um UUID novo): o banco não é
limpo entre testes, mas nenhum teste enxerga as contas do outro.

Quando um passo de PREPARAÇÃO falha, o ajudante para o teste dizendo que
foi a preparação — e não a regra testada — que quebrou. Enquanto a rota
usada na preparação não existir, todo teste que depende dela fica
vermelho por esse motivo: é o TDD mostrando a ordem de implementar.

─────────────────────────────────────────────────────────────────────
O CONTRATO QUE ESTES TESTES ESPERAM (é a RFC, com os detalhes que ela
deixava em aberto já decididos)
─────────────────────────────────────────────────────────────────────
Conta:      {id, event_id, holder_id, holder_type, kind, balance_cents,
             blocked, created_at}
            holder_type é attendee (credencial) ou company (stand) nas
            contas user, e null nas contas do sistema (fee e external),
            que também não têm holder_id. Uma conta de cada tipo por
            evento, e uma conta por dono por evento.
Transação:  {id, idempotency_key, leg, source_account_id,
             destination_account_id, amount_cents, payment_method, status,
             reverses_transaction_id, created_at}
Lote:       POST /internal/transactions e /internal/reversals respondem
            {idempotency_key, transactions: [transação, ...]} na ordem
            em que foram executadas.
Erro:       {title, description, translation, code} (R3)
Todo id que sai é UUID (R5). Recurso que não é de quem chama responde
404 igual ao inexistente (R8). Valor <= 0 em qualquer rota de dinheiro
é 422 QIT002028; valor que não é inteiro ou passa de 10000000 centavos
é 400 (schema). A chave de idempotência das rotas públicas (/transfers e
/recharges) é um UUID; as chaves de Eventos (purchase:, refund:, cash:)
só valem nas rotas internas.
"""

import hashlib
import hmac
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

from tests.utils.services import payments

ERROR_FIELDS = {"title", "description", "translation", "code"}

# O mesmo segredo que o docker-compose.yml entrega à API de Pagamentos.
PIX_WEBHOOK_SECRET = os.environ.get("PIX_WEBHOOK_SECRET", "pix_default_secret")


# ─────────────────────────────────────────────────────────────────────
# Valores novos
# ─────────────────────────────────────────────────────────────────────

def new_uuid() -> str:
    return str(uuid.uuid4())


def new_key(prefix: str = "test") -> str:
    """Uma chave de idempotência nova, no formato das chaves da RFC (purchase:{id})."""
    return f"{prefix}:{uuid.uuid4()}"


def is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False

    return True


# ─────────────────────────────────────────────────────────────────────
# Quem chama
# ─────────────────────────────────────────────────────────────────────

def as_caller(user_id: str, user_type: str = "attendee") -> dict:
    """Os cabeçalhos que o Gateway põe depois de conferir a sessão.

    Nos testes de uma API sozinha, o teste faz o papel do Gateway: é ele
    quem diz quem está chamando. O token já vai pelo `send`.
    """
    return {
        "X-User-Id": user_id,
        "X-User-Type": user_type,
        "X-Request-ID": f"test-{uuid.uuid4().hex}",
    }


# ─────────────────────────────────────────────────────────────────────
# Conferências
# ─────────────────────────────────────────────────────────────────────

def assert_error(response, status: int, code: str) -> None:
    """Confere uma recusa: o status, o código e o formato do corpo (R3)."""
    assert response.status_code == status, (
        f"esperava {status} {code}, veio {response.status_code}: {response.text}"
    )

    body = response.json()
    assert set(body) == ERROR_FIELDS, f"corpo de erro fora do formato da casa: {body}"
    assert body["code"] == code, f"esperava {code}, veio {body['code']}: {body}"


def same_refusal(first, second) -> bool:
    """As duas recusas são indistinguíveis para quem está varrendo ids (R8).

    A descrição fica de fora: ela pode citar o id pedido, que é diferente
    nas duas requisições.
    """
    if first.status_code != second.status_code:
        return False

    a, b = first.json(), second.json()

    return (a["code"], a["title"], a["translation"]) == (b["code"], b["title"], b["translation"])


SETUP_SUCCESS_STATUSES = (200, 201, 204)
NO_CONTENT = 204


def setup_ok(response, what: str = None):
    """Confere um passo de PREPARAÇÃO e devolve o corpo da resposta.

    Toda chamada que só monta o cenário passa por aqui. Sem isto, uma
    preparação que falhou deixaria o teste quebrar mais adiante, numa
    linha que acusa a regra errada.
    """
    what = what or f"{response.request.method} {response.request.path_url}"
    assert response.status_code in SETUP_SUCCESS_STATUSES, (
        f"A PREPARAÇÃO do teste falhou em {what}: {response.status_code} {response.text}\n"
        "O que está quebrado é a rota usada para montar o cenário, não a regra deste teste."
    )

    if response.status_code == NO_CONTENT:
        return None

    return response.json()


# ─────────────────────────────────────────────────────────────────────
# Rotas, chamadas do jeito que a API de Eventos e o Gateway chamariam
# ─────────────────────────────────────────────────────────────────────

ATTENDEE_HOLDER = "attendee"
COMPANY_HOLDER = "company"
MAXIMUM_AMOUNT_CENTS = 10_000_000


def create_account(
    event_id: str,
    kind: str = "user",
    holder_id: str = None,
    idempotency_key: str = None,
    holder_type: str = ATTENDEE_HOLDER,
) -> dict:
    payload = {
        "event_id": event_id,
        "kind": kind,
        "idempotency_key": idempotency_key or new_key("account"),
    }

    if kind == "user":
        payload["holder_id"] = holder_id or new_uuid()
        payload["holder_type"] = holder_type

    response = payments.send("POST", "/internal/accounts", json=payload)

    return setup_ok(response, f"POST /internal/accounts (kind={kind}, holder_type={holder_type})")


def move(transfers: list, payment_method: str = "balance", idempotency_key: str = None):
    """POST /internal/transactions. Devolve a resposta como veio.

    `transfers` é uma lista de (conta_de_origem, conta_de_destino, valor),
    com as contas no formato que a API devolve (só o "id" é usado).
    """
    payload = {
        "idempotency_key": idempotency_key or new_key("tx"),
        "payment_method": payment_method,
        "transfers": [
            {
                "source_account_id": source["id"],
                "destination_account_id": destination["id"],
                "amount_cents": amount,
            }
            for source, destination, amount in transfers
        ],
    }

    return payments.send("POST", "/internal/transactions", json=payload)


def transfer(source, destination, amount_cents, idempotency_key=None, caller=None):
    payload = {
        "source_account_id": source["id"],
        "destination_account_id": destination["id"],
        "amount_cents": amount_cents,
        "idempotency_key": idempotency_key or new_uuid(),
    }

    return payments.send("POST", "/transfers", json=payload, headers=as_caller(caller or source["holder_id"]))


def recharge(account, payment_method, amount_cents, idempotency_key=None, caller=None, **extra_fields):
    payload = {
        "account_id": account["id"],
        "payment_method": payment_method,
        "amount_cents": amount_cents,
        "idempotency_key": idempotency_key or new_uuid(),
    }
    payload.update(extra_fields)

    return payments.send("POST", "/recharges", json=payload, headers=as_caller(caller or account["holder_id"]))


def get_account(account: dict, caller: str = None):
    return payments.send(
        "GET",
        f"/accounts/{account['id']}",
        headers=as_caller(caller or account["holder_id"]),
    )


def balance(account: dict) -> int:
    return setup_ok(get_account(account), "GET /accounts/{id}")["balance_cents"]


def get_transaction(transaction_id: str, caller: str):
    return payments.send("GET", f"/transactions/{transaction_id}", headers=as_caller(caller))


def statement(account: dict, caller: str = None, **params):
    return payments.send(
        "GET",
        f"/accounts/{account['id']}/statement",
        headers=as_caller(caller or account["holder_id"]),
        params=params,
    )


def block(account: dict, blocked: bool = True):
    return payments.send("PUT", f"/internal/accounts/{account['id']}/block", json={"blocked": blocked})


def reverse(original_idempotency_key: str, idempotency_key: str = None):
    return payments.send(
        "POST",
        "/internal/reversals",
        json={
            "original_idempotency_key": original_idempotency_key,
            "idempotency_key": idempotency_key or new_key("refund"),
        },
    )


def pix_webhook(
    transaction_id: str, status: str, amount_cents: int, secret: str = PIX_WEBHOOK_SECRET, reference: str = None
):
    """PUT /webhooks/pix/{id}, como o provedor de Pix chamaria (pelo Gateway).

    A assinatura é um HMAC-SHA256, em hexadecimal, dos bytes EXATOS do
    corpo, com o segredo combinado com o provedor. Vai no cabeçalho
    X-Pix-Signature. Por isso o corpo vai cru (`data`), e não como `json`:
    assinar um texto e mandar outro quebraria a conta.

    O corpo carrega a `reference` que Pagamentos mandou ao criar a cobrança
    (o id da transação): é ela que amarra o aviso assinado a UMA cobrança.
    """
    notice = {"status": status, "amount_cents": amount_cents, "reference": reference or transaction_id}

    return send_signed_pix_notice(transaction_id, notice, secret)


def send_signed_pix_notice(transaction_id: str, notice: dict, secret: str = PIX_WEBHOOK_SECRET):
    body = json.dumps(notice).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    return payments.send(
        "PUT",
        f"/webhooks/pix/{transaction_id}",
        data=body,
        headers={"Content-Type": "application/json", "X-Pix-Signature": signature},
    )


def fire_together(request_function, times: int) -> list:
    with ThreadPoolExecutor(max_workers=times) as pool:
        futures = [pool.submit(request_function) for _ in range(times)]
        return [future.result() for future in futures]


# ─────────────────────────────────────────────────────────────────────
# O cenário mais comum: um evento com as contas do sistema
# ─────────────────────────────────────────────────────────────────────

class Event:
    """Um evento novo, com as duas contas que a API de Eventos abre ao criá-lo."""

    def __init__(self) -> None:
        self.id = new_uuid()
        self.external = create_account(self.id, kind="external")
        self.fee = create_account(self.id, kind="fee")

    def user_account(self, balance_cents: int = 0, holder_id: str = None) -> dict:
        return self._funded_account(ATTENDEE_HOLDER, balance_cents, holder_id)

    def stand_account(self, balance_cents: int = 0, holder_id: str = None) -> dict:
        return self._funded_account(COMPANY_HOLDER, balance_cents, holder_id)

    def _funded_account(self, holder_type: str, balance_cents: int, holder_id: str) -> dict:
        """O saldo entra como a recarga em dinheiro: da external para a conta, método cash."""
        account = create_account(self.id, holder_id=holder_id, holder_type=holder_type)

        if balance_cents > 0:
            setup_ok(
                move([(self.external, account, balance_cents)], payment_method="cash"),
                "a recarga em dinheiro que dá saldo à conta",
            )

        return account

    def reconciliation(self) -> dict:
        response = payments.send("GET", f"/internal/events/{self.id}/reconciliation")
        return setup_ok(response, "GET /internal/events/{id}/reconciliation")

    def balance_of(self, account: dict) -> int:
        """O saldo de qualquer conta do evento, inclusive fee e external.

        Conta de usuário: perguntado pelo dono. Conta do sistema não tem
        dono, então o saldo vem da conciliação.
        """
        if account["kind"] == "user":
            return balance(account)

        for line in self.reconciliation()["accounts"]:
            if line["id"] == account["id"]:
                return line["balance_cents"]

        raise AssertionError(f"a conta {account['id']} não aparece na conciliação do evento {self.id}")

    def purchase(self, buyer: dict, stand: dict, total: int = 4000, fee: int = 200, cashback: int = 80):
        """Público paga o stand, o stand paga a tarifa, a conta fee devolve o cashback."""
        key = new_key("purchase")
        response = move(
            [(buyer, stand, total), (stand, self.fee, fee), (self.fee, buyer, cashback)],
            idempotency_key=key,
        )

        return key, response
