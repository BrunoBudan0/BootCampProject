"""POST /transfers — saldo de uma credencial para outra, no mesmo evento.

Rota pública, pelo Gateway. Pagamentos resolve sozinha, sem chamar
nenhuma outra API. Sem tarifa e sem cashback, porque não houve compra.
Só credencial paga credencial: o stand vende pela compra, que cobra a
tarifa, e as contas do sistema não recebem transferência.

Corpo:     source_account_id, destination_account_id, amount_cents (até
           10000000), idempotency_key (UUID)
Respostas: 201 a transação (payment_method balance) · 200 replay
           · 400 QIT000001 · 403 QIT002004 a origem não é uma credencial
           · 404 QIT002020 a origem não é sua · 409 QIT002021 saldo
           · 409 QIT002022 bloqueada · 409 QIT002025 chave com outro valor
           · 422 QIT002027 o destino não aceita transferência
           · 422 QIT002028 valor <= 0 · 422 QIT002029 mesma conta
           · 422 QIT002030 eventos diferentes
"""

from tests.utils.payments import (
    MAXIMUM_AMOUNT_CENTS,
    Event,
    assert_error,
    balance,
    block,
    new_uuid,
    transfer,
)


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
        key = new_uuid()

        first = transfer(source, destination, 1500, idempotency_key=key)
        second = transfer(source, destination, 1500, idempotency_key=key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert balance(source) == 3500

    def test_amount_at_the_ceiling_is_accepted(self):
        event = Event()
        source = event.user_account(balance_cents=MAXIMUM_AMOUNT_CENTS)
        destination = event.user_account()

        response = transfer(source, destination, MAXIMUM_AMOUNT_CENTS)

        assert response.status_code == 201
        assert balance(destination) == MAXIMUM_AMOUNT_CENTS


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

    def test_amount_above_the_ceiling(self):
        event = Event()
        source = event.user_account(balance_cents=5000)

        response = transfer(source, event.user_account(), MAXIMUM_AMOUNT_CENTS + 1)

        assert_error(response, 400, "QIT000001")
        assert balance(source) == 5000

    def test_same_key_with_another_amount(self):
        event = Event()
        source = event.user_account(balance_cents=5000)
        destination = event.user_account()
        key = new_uuid()
        transfer(source, destination, 1500, idempotency_key=key)

        response = transfer(source, destination, 2000, idempotency_key=key)

        assert_error(response, 409, "QIT002025")
        assert balance(source) == 3500

    def test_key_must_be_a_uuid(self):
        """As chaves purchase: e refund: são da API de Eventos. Se o app
        pudesse usá-las, a empresa ocuparia a chave refund:{compra} de uma
        venda própria e travaria o estorno dela para sempre."""
        event = Event()
        source = event.user_account(balance_cents=5000)

        response = transfer(source, event.user_account(), 100, idempotency_key=f"refund:{new_uuid()}")

        assert_error(response, 400, "QIT000001")
        assert balance(source) == 5000


class TestOnlyAttendeesTransferToAttendees:
    def test_stand_does_not_receive_transfers(self):
        """Pagar o stand por transferência seria uma venda sem compra: sem
        tarifa, sem cashback, sem comprovante e sem baixa de estoque."""
        event = Event()
        source = event.user_account(balance_cents=5000)
        stand = event.stand_account()

        response = transfer(source, stand, 1500)

        assert_error(response, 422, "QIT002027")
        assert balance(source) == 5000
        assert balance(stand) == 0

    def test_fee_account_does_not_receive_transfers(self):
        event = Event()
        source = event.user_account(balance_cents=5000)

        response = transfer(source, event.fee, 1500)

        assert_error(response, 422, "QIT002027")
        assert balance(source) == 5000
        assert event.balance_of(event.fee) == 0

    def test_external_account_does_not_receive_transfers(self):
        event = Event()
        source = event.user_account(balance_cents=5000)

        response = transfer(source, event.external, 1500)

        assert_error(response, 422, "QIT002027")
        assert balance(source) == 5000

    def test_stand_cannot_transfer(self):
        event = Event()
        stand = event.stand_account()
        buyer = event.user_account(balance_cents=5000)
        event.purchase(buyer, stand)

        response = transfer(stand, event.user_account(), 1000)

        assert_error(response, 403, "QIT002004")
        assert balance(stand) == 3800
