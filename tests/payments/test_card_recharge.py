"""POST /recharges com cartão — o dinheiro entra de fora, na hora.

Rota pública, pelo Gateway. O número do cartão nunca entra no sistema: o
app manda só o card_token gerado pelo provedor. Pagamentos pede a
autorização ao provedor ANTES de qualquer escrita; aprovado, grava a
transação external -> conta, método card, já settled.

Aqui o provedor é o Mockserver: cada teste combina o que ele responde e,
no fim, pergunta o que ele recebeu.

Corpo:     account_id, payment_method "card", amount_cents, card_token, idempotency_key
Respostas: 201 a transação · 200 replay · 400 QIT000001 · 404 QIT002020
           · 409 QIT002022 bloqueada · 409 QIT002025 chave com outro valor
           · 422 QIT002028 valor <= 0 · 422 QIT002033 cartão recusado
           · 502 QIT002031 provedor fora ou sem resposta
"""

import pytest

from tests.utils import mockserver
from tests.utils.mockserver import CARD_AUTHORIZATIONS
from tests.utils.payments import Event, as_caller, assert_error, balance, block, new_key, new_uuid
from tests.utils.services import payments

APPROVED = {"status": "approved", "authorization_id": "auth-123"}
DECLINED = {"status": "declined", "reason": "insufficient_funds"}


@pytest.fixture(autouse=True)
def clean_provider():
    """O ator é um só para a suíte: cada teste começa sem roteiro herdado."""
    mockserver.reset()
    yield
    mockserver.reset()


def recharge_by_card(account, amount, card_token=None, idempotency_key=None, caller=None, **extra):
    payload = {
        "account_id": account["id"],
        "payment_method": "card",
        "amount_cents": amount,
        "card_token": card_token or f"tok-{new_uuid()}",
        "idempotency_key": idempotency_key or new_key("recharge"),
    }
    payload.update(extra)

    return payments.send("POST", "/recharges", json=payload, headers=as_caller(caller or account["holder_id"]))


def provider_was_called(times, **fields):
    return mockserver.received("POST", CARD_AUTHORIZATIONS, times, fields or None)


class TestCardRecharge:
    def test_approved_card_credits_right_away(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)
        event = Event()
        account = event.user_account()

        response = recharge_by_card(account, 5000, card_token="tok-approved-1")

        assert response.status_code == 201
        assert response.json()["status"] == "settled"
        assert response.json()["payment_method"] == "card"
        assert response.json()["source_account_id"] == event.external["id"]
        assert response.json()["destination_account_id"] == account["id"]
        assert balance(account) == 5000
        assert event.balance_of(event.external) == -5000
        assert provider_was_called(1, card_token="tok-approved-1", amount_cents=5000)

    def test_same_key_does_not_charge_the_card_twice(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)
        account = Event().user_account()
        key = new_key("recharge")

        first = recharge_by_card(account, 5000, card_token="tok-once", idempotency_key=key)
        second = recharge_by_card(account, 5000, card_token="tok-once", idempotency_key=key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert balance(account) == 5000
        assert provider_was_called(1, card_token="tok-once")


class TestCardRechargeFailures:
    def test_declined_card_credits_nothing(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, DECLINED)
        account = Event().user_account()

        assert_error(recharge_by_card(account, 5000), 422, "QIT002033")
        assert balance(account) == 0

    def test_provider_error_is_a_bad_gateway(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 500, {"error": "boom"})
        account = Event().user_account()

        assert_error(recharge_by_card(account, 5000), 502, "QIT002031")
        assert balance(account) == 0

    def test_provider_without_json_is_a_bad_gateway(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200)
        account = Event().user_account()

        assert_error(recharge_by_card(account, 5000), 502, "QIT002031")
        assert balance(account) == 0

    def test_provider_timeout_is_a_bad_gateway_and_credits_nothing(self):
        """O provedor demora mais que o prazo (3 s). A pessoa PODE ter sido
        cobrada — é o log crítico CARD_OUTCOME_UNKNOWN —, mas nenhum saldo
        entra sem a aprovação."""
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED, delay_seconds=6)
        account = Event().user_account()

        assert_error(recharge_by_card(account, 5000), 502, "QIT002031")
        assert balance(account) == 0


class TestCardRechargeRefusals:
    def test_account_of_someone_else(self):
        account = Event().user_account()

        assert_error(recharge_by_card(account, 5000, caller=new_uuid()), 404, "QIT002020")
        assert provider_was_called(0)

    def test_blocked_account(self):
        account = Event().user_account()
        block(account)

        assert_error(recharge_by_card(account, 5000), 409, "QIT002022")
        assert provider_was_called(0)

    def test_zero_amount(self):
        account = Event().user_account()

        assert_error(recharge_by_card(account, 0), 422, "QIT002028")
        assert provider_was_called(0)

    def test_card_without_token(self):
        account = Event().user_account()
        payload = {
            "account_id": account["id"],
            "payment_method": "card",
            "amount_cents": 5000,
            "idempotency_key": new_key("recharge"),
        }

        response = payments.send("POST", "/recharges", json=payload, headers=as_caller(account["holder_id"]))

        assert_error(response, 400, "QIT000001")

    def test_same_key_with_another_amount(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)
        account = Event().user_account()
        key = new_key("recharge")
        recharge_by_card(account, 5000, idempotency_key=key)

        assert_error(recharge_by_card(account, 7000, idempotency_key=key), 409, "QIT002025")
        assert balance(account) == 5000

    def test_cash_is_not_a_recharge_method_here(self):
        """Dinheiro em espécie não tem prova externa: só o organizador lança,
        pela API de Eventos. Por esta rota, só card e pix."""
        account = Event().user_account()

        response = recharge_by_card(account, 5000, payment_method="cash")

        assert_error(response, 400, "QIT000001")
