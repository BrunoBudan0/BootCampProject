"""POST /recharges com Pix e PUT /webhooks/pix/{id}: pagamento e crédito em dois tempos.

1. A recarga grava a transação external -> conta como PENDING e faz
   COMMIT antes de pedir a cobrança ao provedor: a mesma chave chegando
   junta não cria uma segunda cobrança. Provedor fora: a transação vira
   canceled. Nenhum saldo mexe; a resposta traz o copia e cola.
2. A pessoa paga no banco dela. Nada fica esperando.
3. O provedor chama o webhook. Quem autentica é a assinatura (HMAC do
   corpo), não um token, e o corpo traz a `reference` da cobrança (o id da
   transação): um aviso assinado só vale para a cobrança dele. Pago: a
   transação vira settled e o saldo entra, mesmo com a conta bloqueada.
   Expirado: vira canceled, e nenhum saldo entra.

O {id} do webhook é o id da transação devolvido na recarga.

Recarga:   201 {transação pending + pix_copy_paste, expires_at} · 200 replay
           · 400 QIT000001 · 404 QIT002020 · 409 QIT002022 bloqueada
           · 409 QIT002037 evento sem external · 502 QIT002031 provedor fora
Webhook:   204 · 400 QIT000001 · 401 QIT002034 assinatura inválida ou de
           outra cobrança · 404 QIT002023 · 409 QIT002024 transição inválida
           · 422 QIT002035 valor diferente
"""

import pytest

from tests.utils import mockserver
from tests.utils.mockserver import CARD_AUTHORIZATIONS, PIX_CHARGES, PIX_COPY_PASTE, pix_charge_answer
from tests.utils.payments import (
    MAXIMUM_AMOUNT_CENTS,
    Event,
    assert_error,
    balance,
    block,
    create_account,
    fire_together,
    get_transaction,
    new_uuid,
    pix_webhook,
    recharge,
    send_signed_pix_notice,
    setup_ok,
    statement,
)

PARALLEL_REQUESTS = 5


@pytest.fixture(autouse=True)
def provider_creates_charges():
    """Todo teste daqui começa com o Mockserver limpo e criando cobranças."""
    mockserver.reset()
    mockserver.expect("POST", PIX_CHARGES, 201, pix_charge_answer())
    yield
    mockserver.reset()


def recharge_by_pix(account, amount_cents, **options):
    return recharge(account, "pix", amount_cents, **options)


def pending_pix(amount_cents=5000):
    """Uma conta com uma recarga Pix criada e ainda não paga."""
    account = Event().user_account()
    response = recharge_by_pix(account, amount_cents)
    assert response.status_code == 201, f"A preparação (a recarga Pix) falhou: {response.text}"

    return account, response.json()


def status_of(transaction, account):
    return get_transaction(transaction["id"], caller=account["holder_id"]).json()["status"]


def provider_was_called(times, **fields):
    return mockserver.received("POST", PIX_CHARGES, times, fields or None)


class TestPixCharge:
    def test_creates_a_pending_charge_without_touching_the_balance(self):
        account = Event().user_account()

        response = recharge_by_pix(account, 5000)

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending"
        assert body["payment_method"] == "pix"
        assert body["amount_cents"] == 5000
        assert body["pix_copy_paste"] == PIX_COPY_PASTE
        assert body["expires_at"]
        assert balance(account) == 0
        assert provider_was_called(1, amount_cents=5000, reference=body["id"])

    def test_pending_pix_is_not_in_the_statement(self):
        account, _ = pending_pix()

        assert statement(account).json()["data"] == []

    def test_same_key_returns_the_same_charge(self):
        account = Event().user_account()
        key = new_uuid()

        first = recharge_by_pix(account, 5000, idempotency_key=key)
        second = recharge_by_pix(account, 5000, idempotency_key=key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["pix_copy_paste"] == first.json()["pix_copy_paste"]
        assert provider_was_called(1)

    def test_parallel_requests_with_the_same_key_create_one_charge(self):
        account = Event().user_account()
        key = new_uuid()

        responses = fire_together(lambda: recharge_by_pix(account, 5000, idempotency_key=key), PARALLEL_REQUESTS)

        statuses = [response.status_code for response in responses]
        assert statuses.count(201) == 1, statuses
        assert statuses.count(200) == PARALLEL_REQUESTS - 1, statuses
        assert len({response.json()["id"] for response in responses}) == 1
        assert provider_was_called(1)

    def test_provider_down_cancels_the_charge_and_the_resend_says_so(self):
        mockserver.reset()
        mockserver.expect("POST", PIX_CHARGES, 500, {"error": "boom"})
        account = Event().user_account()
        key = new_uuid()

        first = recharge_by_pix(account, 5000, idempotency_key=key)
        resent = recharge_by_pix(account, 5000, idempotency_key=key)

        assert_error(first, 502, "QIT002031")
        assert resent.status_code == 200
        assert resent.json()["status"] == "canceled"
        assert resent.json()["pix_copy_paste"] is None
        assert statement(account).json()["data"] == []
        assert balance(account) == 0
        assert provider_was_called(1)


class TestPixChargeRefusals:
    def test_account_of_someone_else(self):
        account = Event().user_account()

        assert_error(recharge_by_pix(account, 5000, caller=new_uuid()), 404, "QIT002020")
        assert provider_was_called(0)

    def test_blocked_account(self):
        account = Event().user_account()
        setup_ok(block(account))

        assert_error(recharge_by_pix(account, 5000), 409, "QIT002022")
        assert provider_was_called(0)

    def test_amount_above_the_ceiling(self):
        account = Event().user_account()

        assert_error(recharge_by_pix(account, MAXIMUM_AMOUNT_CENTS + 1), 400, "QIT000001")
        assert provider_was_called(0)

    def test_event_without_external_account(self):
        account = create_account(new_uuid())

        assert_error(recharge_by_pix(account, 5000), 409, "QIT002037")
        assert provider_was_called(0)


class TestPixWebhook:
    def test_paid_webhook_credits_the_account(self):
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "paid", 5000)

        assert response.status_code == 204
        assert balance(account) == 5000
        assert status_of(transaction, account) == "settled"

    def test_second_paid_notice_does_not_credit_twice(self):
        account, transaction = pending_pix(5000)
        setup_ok(pix_webhook(transaction["id"], "paid", 5000))

        response = pix_webhook(transaction["id"], "paid", 5000)

        assert response.status_code == 204
        assert balance(account) == 5000

    def test_expired_charge_is_canceled_without_credit(self):
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "expired", 5000)

        assert response.status_code == 204
        assert balance(account) == 0
        assert status_of(transaction, account) == "canceled"

    def test_paid_pix_credits_a_blocked_account(self):
        """O dinheiro já saiu do banco da pessoa: o bloqueio impede gastar, não receber o que ela pagou."""
        account, transaction = pending_pix(5000)
        setup_ok(block(account))

        response = pix_webhook(transaction["id"], "paid", 5000)

        assert response.status_code == 204
        assert balance(account) == 5000
        assert status_of(transaction, account) == "settled"


class TestPixWebhookRefusals:
    def test_invalid_signature_is_refused(self):
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "paid", 5000, secret="segredo-errado")

        assert_error(response, 401, "QIT002034")
        assert balance(account) == 0
        assert status_of(transaction, account) == "pending"

    def test_paid_notice_of_another_charge_is_refused(self):
        account_a, charge_a = pending_pix(5000)
        account_b, charge_b = pending_pix(5000)

        response = pix_webhook(charge_b["id"], "paid", 5000, reference=charge_a["id"])

        assert_error(response, 401, "QIT002034")
        assert balance(account_b) == 0
        assert status_of(charge_b, account_b) == "pending"
        assert status_of(charge_a, account_a) == "pending"

    def test_expired_notice_of_another_charge_does_not_cancel_it(self):
        account_a, charge_a = pending_pix(5000)
        account_b, charge_b = pending_pix(5000)

        response = pix_webhook(charge_b["id"], "expired", 5000, reference=charge_a["id"])

        assert_error(response, 401, "QIT002034")
        assert status_of(charge_b, account_b) == "pending"
        assert status_of(charge_a, account_a) == "pending"

    def test_notice_without_reference_is_refused(self):
        account, transaction = pending_pix(5000)

        response = send_signed_pix_notice(transaction["id"], {"status": "paid", "amount_cents": 5000})

        assert_error(response, 400, "QIT000001")
        assert balance(account) == 0

    def test_paid_amount_above_the_recharge_ceiling_is_a_mismatch(self):
        """Nenhuma cobrança passa do teto, então um aviso acima dele é sempre
        divergência de valor: responde como tal, e o alarme toca."""
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "paid", MAXIMUM_AMOUNT_CENTS + 1)

        assert_error(response, 422, "QIT002035")
        assert balance(account) == 0

    def test_paid_amount_beyond_what_the_database_holds_is_refused(self):
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "paid", 2**63)

        assert_error(response, 400, "QIT000001")
        assert balance(account) == 0

    def test_paid_amount_different_from_the_charge(self):
        account, transaction = pending_pix(5000)

        response = pix_webhook(transaction["id"], "paid", 4000)

        assert_error(response, 422, "QIT002035")
        assert balance(account) == 0

    def test_paid_after_expired_is_an_invalid_transition(self):
        account, transaction = pending_pix(5000)
        setup_ok(pix_webhook(transaction["id"], "expired", 5000))

        response = pix_webhook(transaction["id"], "paid", 5000)

        assert_error(response, 409, "QIT002024")
        assert balance(account) == 0

    def test_unknown_transaction(self):
        assert_error(pix_webhook(new_uuid(), "paid", 5000), 404, "QIT002023")

    def test_notice_for_a_card_recharge_is_not_found(self):
        """O webhook só conhece transações Pix: o id de uma recarga de cartão
        responde como um id que não existe, mesmo com assinatura válida."""
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, {"status": "approved", "authorization_id": "auth-1"})
        account = Event().user_account()
        card_recharge = setup_ok(recharge(account, "card", 5000, card_token="tok-card"))

        response = pix_webhook(card_recharge["id"], "paid", 5000)

        assert_error(response, 404, "QIT002023")
        assert balance(account) == 5000
