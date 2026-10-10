"""POST /recharges com Pix e PUT /webhooks/pix/{id} — pagamento e crédito em dois tempos.

1. A recarga pede a cobrança ao provedor e grava a transação external ->
   conta como PENDING, sem mexer em saldo. Responde o copia e cola.
2. A pessoa paga no banco dela. Nada fica esperando.
3. O provedor chama o webhook. Quem autentica é a assinatura (HMAC do
   corpo), não um token. Pago: a transação vira settled e o saldo entra.
   Expirado: vira canceled, e nenhum saldo entra.

O {id} do webhook é o id da transação devolvido na recarga.

Recarga:   201 {transação pending + pix_copy_paste, expires_at} · 200 replay
           · 502 QIT002031 provedor fora
Webhook:   204 · 401 QIT002034 assinatura inválida · 404 QIT002023
           · 409 QIT002024 transição inválida · 422 QIT002035 valor diferente
"""

import pytest

from tests.utils import mockserver
from tests.utils.mockserver import PIX_CHARGES
from tests.utils.payments import (
    Event,
    as_caller,
    assert_error,
    balance,
    get_transaction,
    new_key,
    new_uuid,
    pix_webhook,
    statement,
)
from tests.utils.services import payments

CHARGE = {
    "charge_id": "charge-123",
    "copy_paste": "00020126580014br.gov.bcb.pix0136teste-banco-de-eventos",
    "expires_at": "2026-12-31T23:59:59+00:00",
}


@pytest.fixture(autouse=True)
def provider_creates_charges():
    """Todo teste daqui começa com o ator limpo e criando cobranças."""
    mockserver.reset()
    mockserver.expect("POST", PIX_CHARGES, 201, CHARGE)
    yield
    mockserver.reset()


def recharge_by_pix(account, amount, idempotency_key=None):
    payload = {
        "account_id": account["id"],
        "payment_method": "pix",
        "amount_cents": amount,
        "idempotency_key": idempotency_key or new_key("recharge"),
    }

    return payments.send("POST", "/recharges", json=payload, headers=as_caller(account["holder_id"]))


def pending_pix(amount=5000):
    """Uma conta com uma recarga Pix criada e ainda não paga."""
    account = Event().user_account()
    response = recharge_by_pix(account, amount)
    assert response.status_code == 201, f"A PREPARAÇÃO (a recarga Pix) falhou: {response.text}"

    return account, response.json()


def status_of(transaction, account):
    return get_transaction(transaction["id"], caller=account["holder_id"]).json()["status"]


class TestPixCharge:
    def test_creates_a_pending_charge_without_touching_the_balance(self):
        account = Event().user_account()

        response = recharge_by_pix(account, 5000)

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending"
        assert body["payment_method"] == "pix"
        assert body["amount_cents"] == 5000
        assert body["pix_copy_paste"] == CHARGE["copy_paste"]
        assert body["expires_at"]
        assert balance(account) == 0
        assert mockserver.received("POST", PIX_CHARGES, 1, {"amount_cents": 5000})

    def test_pending_pix_is_not_in_the_statement(self):
        account, _ = pending_pix()

        assert statement(account).json()["data"] == []

    def test_same_key_returns_the_same_charge(self):
        account = Event().user_account()
        key = new_key("recharge")

        first = recharge_by_pix(account, 5000, idempotency_key=key)
        second = recharge_by_pix(account, 5000, idempotency_key=key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["pix_copy_paste"] == first.json()["pix_copy_paste"]
        assert mockserver.received("POST", PIX_CHARGES, 1)

    def test_provider_down_records_nothing(self):
        mockserver.reset()
        mockserver.expect("POST", PIX_CHARGES, 500, {"error": "boom"})
        account = Event().user_account()

        assert_error(recharge_by_pix(account, 5000), 502, "QIT002031")
        assert statement(account).json()["data"] == []


class TestPixWebhook:
    def test_paid_webhook_credits_the_account(self):
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "paid", 5000)

        assert response.status_code == 204
        assert balance(account) == 5000
        assert status_of(transaction, account) == "settled"

    def test_second_paid_notice_does_not_credit_twice(self):
        account, transaction = pending_pix(5000)
        pix_webhook(transaction["id"], "paid", 5000)

        response = pix_webhook(transaction["id"], "paid", 5000)

        assert response.status_code == 204
        assert balance(account) == 5000

    def test_expired_charge_is_canceled_without_credit(self):
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "expired", 5000)

        assert response.status_code == 204
        assert balance(account) == 0
        assert status_of(transaction, account) == "canceled"


class TestPixWebhookRefusals:
    def test_invalid_signature_is_refused(self):
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "paid", 5000, secret="segredo-errado")

        assert_error(response, 401, "QIT002034")
        assert balance(account) == 0
        assert status_of(transaction, account) == "pending"

    def test_paid_amount_different_from_the_charge(self):
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "paid", 4000)

        assert_error(response, 422, "QIT002035")
        assert balance(account) == 0

    def test_paid_after_expired_is_an_invalid_transition(self):
        account, transaction = pending_pix(5000)
        pix_webhook(transaction["id"], "expired", 5000)

        response = pix_webhook(transaction["id"], "paid", 5000)

        assert_error(response, 409, "QIT002024")
        assert balance(account) == 0

    def test_unknown_transaction(self):
        assert_error(pix_webhook(new_uuid(), "paid", 5000), 404, "QIT002023")
