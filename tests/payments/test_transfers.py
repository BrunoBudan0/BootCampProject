"""POST /transfers — saldo de uma credencial para outra, no mesmo evento.

Rota pública, pelo Gateway. Pagamentos resolve sozinha, sem chamar
nenhuma outra API. Sem tarifa e sem cashback, porque não houve compra.

Corpo:     source_account_id, destination_account_id, amount_cents, idempotency_key
Respostas: 201 a transação (payment_method balance) · 200 replay
           · 404 QIT002020 a origem não é sua · 409 QIT002021 saldo
           · 409 QIT002022 bloqueada · 409 QIT002025 chave com outro valor
           · 422 QIT002028 valor <= 0 · 422 QIT002029 mesma conta
           · 422 QIT002030 eventos diferentes
"""

from tests.utils.payments import Event, as_caller, assert_error, balance, block, new_key, new_uuid
from tests.utils.services import payments


def transfer(source, destination, amount, idempotency_key=None, caller=None):
    payload = {
        "source_account_id": source["id"],
        "destination_account_id": destination["id"],
        "amount_cents": amount,
        "idempotency_key": idempotency_key or new_key("transfer"),
    }

    return payments.send("POST", "/transfers", json=payload, headers=as_caller(caller or source["holder_id"]))


class TestTransfer:
    def test_moves_balance_without_fee(self):
        event = Event()
        source = event.user_account(balance_cents=5000)
        destination = event.user_account()

        response = transfer(source, destination, 1500)

        assert response.status_code == 201
        assert response.json()["payment_method"] == "balance"
        assert response.json()["amount_cents"] == 1500
        assert balance(source) == 3500
        assert balance(destination) == 1500
        assert event.balance_of(event.fee) == 0

    def test_same_key_replays_without_moving_again(self):
        event = Event()
        source = event.user_account(balance_cents=5000)
        destination = event.user_account()
        key = new_key("transfer")

        first = transfer(source, destination, 1500, idempotency_key=key)
        second = transfer(source, destination, 1500, idempotency_key=key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert balance(source) == 3500


class TestTransferRefusals:
    def test_source_must_belong_to_the_caller(self):
        event = Event()
        source = event.user_account(balance_cents=5000)
        destination = event.user_account()

        response = transfer(source, destination, 1500, caller=destination["holder_id"])

        assert_error(response, 404, "QIT002020")
        assert balance(source) == 5000

    def test_missing_destination(self):
        source = Event().user_account(balance_cents=5000)

        response = transfer(source, {"id": new_uuid()}, 1500)

        assert_error(response, 404, "QIT002020")
        assert balance(source) == 5000

    def test_insufficient_balance(self):
        event = Event()
        source = event.user_account(balance_cents=1000)

        assert_error(transfer(source, event.user_account(), 1500), 409, "QIT002021")
        assert balance(source) == 1000

    def test_blocked_source(self):
        event = Event()
        source = event.user_account(balance_cents=5000)
        block(source)

        assert_error(transfer(source, event.user_account(), 1500), 409, "QIT002022")

    def test_blocked_destination(self):
        event = Event()
        source = event.user_account(balance_cents=5000)
        destination = event.user_account()
        block(destination)

        assert_error(transfer(source, destination, 1500), 409, "QIT002022")
        assert balance(source) == 5000

    def test_same_account(self):
        source = Event().user_account(balance_cents=5000)

        assert_error(transfer(source, source, 1500), 422, "QIT002029")

    def test_accounts_of_different_events(self):
        source = Event().user_account(balance_cents=5000)
        destination = Event().user_account()

        assert_error(transfer(source, destination, 1500), 422, "QIT002030")
        assert balance(source) == 5000

    def test_zero_amount(self):
        event = Event()
        source = event.user_account(balance_cents=5000)

        assert_error(transfer(source, event.user_account(), 0), 422, "QIT002028")

    def test_same_key_with_another_amount(self):
        event = Event()
        source = event.user_account(balance_cents=5000)
        destination = event.user_account()
        key = new_key("transfer")
        transfer(source, destination, 1500, idempotency_key=key)

        response = transfer(source, destination, 2000, idempotency_key=key)

        assert_error(response, 409, "QIT002025")
        assert balance(source) == 3500
