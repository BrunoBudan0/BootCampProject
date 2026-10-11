"""POST /recharges com cartão — o dinheiro entra de fora, na hora.

Rota pública, pelo Gateway. O número do cartão nunca entra no sistema: o
app manda só o card_token gerado pelo provedor.

A recarga acontece em três tempos, para que nenhuma cobrança aconteça
duas vezes:
  1. grava a transação external -> conta como pending, com a chave, e faz
     COMMIT. Uma segunda requisição com a mesma chave já encontra essa
     linha e não chama o provedor;
  2. pede a autorização ao provedor, fora de qualquer transação de banco;
  3. aprovado: a transação vira settled e o saldo entra, mesmo que a
     conta tenha sido bloqueada no meio do caminho (a pessoa já pagou).
     Recusado: canceled. Sem resposta: continua pending, com log crítico.
O reenvio com a mesma chave devolve a transação como ela está (200), e o
app lê o status. Recarga recusada não se repete com a mesma chave.

Aqui o provedor é o Mockserver: cada teste combina o que ele responde e,
no fim, pergunta o que ele recebeu.

Corpo:     account_id, payment_method "card", amount_cents (até 10000000),
           card_token, idempotency_key (UUID)
Respostas: 201 a transação · 200 replay · 400 QIT000001 · 404 QIT002020
           · 409 QIT002022 bloqueada · 409 QIT002025 chave com outro valor
           · 409 QIT002037 o evento não tem a conta external
           · 422 QIT002028 valor <= 0 · 422 QIT002033 cartão recusado
           · 502 QIT002031 provedor fora ou sem resposta
"""

import threading
import time

import pytest

from tests.utils import mockserver
from tests.utils.mockserver import CARD_AUTHORIZATIONS
from tests.utils.payments import (
    MAXIMUM_AMOUNT_CENTS,
    Event,
    as_caller,
    assert_error,
    balance,
    block,
    create_account,
    fire_together,
    new_uuid,
    recharge,
)
from tests.utils.services import payments

APPROVED = {"status": "approved", "authorization_id": "auth-123"}
DECLINED = {"status": "declined", "reason": "insufficient_funds"}
PARALLEL_REQUESTS = 5


@pytest.fixture(autouse=True)
def clean_provider():
    """O ator é um só para a suíte: cada teste começa sem roteiro herdado."""
    mockserver.reset()
    yield
    mockserver.reset()


def recharge_by_card(account, amount_cents, card_token=None, **options):
    return recharge(account, "card", amount_cents, card_token=card_token or f"tok-{new_uuid()}", **options)


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
        key = new_uuid()

        first = recharge_by_card(account, 5000, card_token="tok-once", idempotency_key=key)
        second = recharge_by_card(account, 5000, card_token="tok-once", idempotency_key=key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert balance(account) == 5000
        assert provider_was_called(1, card_token="tok-once")

    def test_parallel_requests_with_the_same_key_charge_the_card_once(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)
        account = Event().user_account()
        key = new_uuid()

        responses = fire_together(
            lambda: recharge_by_card(account, 5000, card_token="tok-double-click", idempotency_key=key),
            PARALLEL_REQUESTS,
        )

        statuses = [response.status_code for response in responses]
        assert statuses.count(201) == 1, statuses
        assert statuses.count(200) == PARALLEL_REQUESTS - 1, statuses
        assert len({response.json()["id"] for response in responses}) == 1
        assert balance(account) == 5000
        assert provider_was_called(1, card_token="tok-double-click")

    def test_card_approved_while_the_account_was_blocked_still_credits(self):
        """A pessoa já foi cobrada quando o bloqueio chegou: o dinheiro é dela."""
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED, delay_seconds=2)
        account = Event().user_account()
        responses = []
        recharging = threading.Thread(target=lambda: responses.append(recharge_by_card(account, 5000)))

        recharging.start()
        time.sleep(1)
        block(account)
        recharging.join()

        assert responses[0].status_code == 201, responses[0].text
        assert responses[0].json()["status"] == "settled"
        assert balance(account) == 5000


class TestCardRechargeFailures:
    def test_declined_card_credits_nothing(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, DECLINED)
        account = Event().user_account()

        assert_error(recharge_by_card(account, 5000), 422, "QIT002033")
        assert balance(account) == 0

    def test_declined_recharge_is_not_retried_with_the_same_key(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, DECLINED)
        account = Event().user_account()
        key = new_uuid()
        recharge_by_card(account, 5000, idempotency_key=key)
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)

        response = recharge_by_card(account, 5000, idempotency_key=key)

        assert response.status_code == 200
        assert response.json()["status"] == "canceled"
        assert balance(account) == 0
        assert provider_was_called(1)

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

    def test_resend_after_a_timeout_returns_the_pending_recharge(self):
        """Sem saber se a pessoa foi cobrada, o sistema não cobra de novo."""
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED, delay_seconds=6)
        account = Event().user_account()
        key = new_uuid()
        recharge_by_card(account, 5000, idempotency_key=key)

        response = recharge_by_card(account, 5000, idempotency_key=key)

        assert response.status_code == 200
        assert response.json()["status"] == "pending"
        assert balance(account) == 0
        assert provider_was_called(1)


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

    def test_amount_above_the_ceiling(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)
        account = Event().user_account()

        assert_error(recharge_by_card(account, MAXIMUM_AMOUNT_CENTS + 1), 400, "QIT000001")
        assert provider_was_called(0)

    def test_amount_far_above_the_ceiling_is_not_a_server_error(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)
        account = Event().user_account()

        assert_error(recharge_by_card(account, 10**19), 400, "QIT000001")
        assert provider_was_called(0)

    def test_event_without_external_account(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)
        account = create_account(new_uuid())

        assert_error(recharge_by_card(account, 5000), 409, "QIT002037")
        assert provider_was_called(0)

    def test_key_must_be_a_uuid(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)
        account = Event().user_account()

        response = recharge_by_card(account, 5000, idempotency_key=f"refund:{new_uuid()}")

        assert_error(response, 400, "QIT000001")
        assert provider_was_called(0)

    def test_card_without_token(self):
        account = Event().user_account()
        payload = {
            "account_id": account["id"],
            "payment_method": "card",
            "amount_cents": 5000,
            "idempotency_key": new_uuid(),
        }

        response = payments.send("POST", "/recharges", json=payload, headers=as_caller(account["holder_id"]))

        assert_error(response, 400, "QIT000001")

    def test_same_key_with_another_amount(self):
        mockserver.expect("POST", CARD_AUTHORIZATIONS, 200, APPROVED)
        account = Event().user_account()
        key = new_uuid()
        recharge_by_card(account, 5000, idempotency_key=key)

        assert_error(recharge_by_card(account, 7000, idempotency_key=key), 409, "QIT002025")
        assert balance(account) == 5000

    def test_cash_is_not_a_recharge_method_here(self):
        """Dinheiro em espécie não tem prova externa: só o organizador lança,
        pela API de Eventos. Por esta rota, só card e pix."""
        account = Event().user_account()

        response = recharge(account, "cash", 5000, card_token="tok-cash")

        assert_error(response, 400, "QIT000001")
