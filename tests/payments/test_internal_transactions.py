"""POST /internal/transactions — mover dinheiro.

Quem chama é a API de Eventos (compra e recarga em dinheiro). Uma ou
mais transferências executam JUNTAS, na ordem enviada: todas ou nenhuma.

Corpo:     idempotency_key, payment_method (balance | card | pix | cash),
           transfers: [{source_account_id, destination_account_id,
           amount_cents (até 10000000)}]
Respostas: 201 {idempotency_key, transactions} · 200 replay · 400 QIT000001
           · 404 QIT002020 conta inexistente · 409 QIT002021 saldo
           · 409 QIT002022 bloqueada · 409 QIT002025 chave com outro conteúdo
           · 422 QIT002028 valor <= 0 · 422 QIT002029 mesma conta
           · 422 QIT002030 contas de eventos diferentes

A regra que nenhum teste daqui pode ver quebrar: conta de usuário nunca
fica negativa, e numa recusa NADA se move.
"""

from tests.utils.payments import (
    MAXIMUM_AMOUNT_CENTS,
    Event,
    assert_error,
    balance,
    is_uuid,
    move,
    new_key,
    new_uuid,
    setup_ok,
)
from tests.utils.services import payments


class TestMovesMoney:
    def test_cash_recharge_moves_from_external_to_user(self):
        event = Event()
        account = event.user_account()

        response = move([(event.external, account, 5000)], payment_method="cash")

        assert response.status_code == 201
        transactions = response.json()["transactions"]
        assert len(transactions) == 1
        transaction = transactions[0]
        assert is_uuid(transaction["id"])
        assert transaction["leg"] == 1
        assert transaction["source_account_id"] == event.external["id"]
        assert transaction["destination_account_id"] == account["id"]
        assert transaction["amount_cents"] == 5000
        assert transaction["payment_method"] == "cash"
        assert transaction["status"] == "settled"
        assert transaction["reverses_transaction_id"] is None
        assert balance(account) == 5000

    def test_amount_at_the_ceiling_is_accepted(self):
        event = Event()
        account = event.user_account()

        response = move([(event.external, account, MAXIMUM_AMOUNT_CENTS)], payment_method="cash")

        assert response.status_code == 201
        assert balance(account) == MAXIMUM_AMOUNT_CENTS

    def test_external_account_goes_negative_on_purpose(self):
        """O módulo da external é quanto dinheiro entrou de fora."""
        event = Event()
        event.user_account(balance_cents=5000)

        assert event.balance_of(event.external) == -5000

    def test_purchase_moves_price_fee_and_cashback(self):
        """O exemplo da RFC: compra de R$ 40, tarifa de 5%, cashback de 2%."""
        event = Event()
        buyer = event.user_account(balance_cents=5000)
        stand = event.stand_account()

        key, response = event.purchase(buyer, stand, total=4000, fee=200, cashback=80)

        assert response.status_code == 201
        assert response.json()["idempotency_key"] == key
        legs = [transaction["leg"] for transaction in response.json()["transactions"]]
        assert legs == [1, 2, 3]
        assert balance(buyer) == 5000 - 4000 + 80
        assert balance(stand) == 4000 - 200
        assert event.balance_of(event.fee) == 200 - 80

    def test_event_still_sums_to_zero_after_a_purchase(self):
        event = Event()
        buyer = event.user_account(balance_cents=5000)
        stand = event.stand_account()
        setup_ok(event.purchase(buyer, stand)[1])

        reconciliation = event.reconciliation()

        assert reconciliation["sum_cents"] == 0
        assert reconciliation["mismatches"] == []


class TestRefusesWithoutMovingAnything:
    def test_insufficient_balance(self):
        event = Event()
        buyer = event.user_account(balance_cents=1000)
        stand = event.stand_account()

        response = move([(buyer, stand, 4000)])

        assert_error(response, 409, "QIT002021")
        assert balance(buyer) == 1000
        assert balance(stand) == 0

    def test_all_or_nothing(self):
        """A primeira transferência caberia; a segunda não. Nenhuma acontece."""
        event = Event()
        buyer = event.user_account(balance_cents=5000)
        stand = event.stand_account()

        response = move([(buyer, stand, 4000), (buyer, stand, 2000)])

        assert_error(response, 409, "QIT002021")
        assert balance(buyer) == 5000
        assert balance(stand) == 0

    def test_missing_source_account(self):
        account = Event().user_account()

        assert_error(move([({"id": new_uuid()}, account, 100)]), 404, "QIT002020")

    def test_missing_destination_account(self):
        account = Event().user_account(balance_cents=1000)

        response = move([(account, {"id": new_uuid()}, 100)])

        assert_error(response, 404, "QIT002020")
        assert balance(account) == 1000

    def test_same_account_on_both_sides(self):
        account = Event().user_account(balance_cents=1000)

        assert_error(move([(account, account, 100)]), 422, "QIT002029")
        assert balance(account) == 1000

    def test_accounts_of_different_events(self):
        payer = Event().user_account(balance_cents=1000)
        receiver = Event().user_account()

        response = move([(payer, receiver, 100)])

        assert_error(response, 422, "QIT002030")
        assert balance(payer) == 1000
        assert balance(receiver) == 0

    def test_zero_amount(self):
        event = Event()
        account = event.user_account(balance_cents=1000)

        assert_error(move([(account, event.user_account(), 0)]), 422, "QIT002028")
        assert balance(account) == 1000

    def test_negative_amount(self):
        """Valor negativo seria uma transferência ao contrário, disfarçada."""
        event = Event()
        payer = event.user_account()
        receiver = event.user_account(balance_cents=1000)

        response = move([(payer, receiver, -500)])

        assert_error(response, 422, "QIT002028")
        assert balance(receiver) == 1000

    def test_amount_above_the_ceiling(self):
        event = Event()
        account = event.user_account(balance_cents=1000)

        response = move([(account, event.user_account(), MAXIMUM_AMOUNT_CENTS + 1)])

        assert_error(response, 400, "QIT000001")
        assert balance(account) == 1000

    def test_amount_must_be_an_integer(self):
        event = Event()
        account = event.user_account(balance_cents=1000)

        assert_error(move([(account, event.user_account(), 10.5)]), 400, "QIT000001")
        assert balance(account) == 1000

    def test_unknown_payment_method(self):
        event = Event()
        account = event.user_account(balance_cents=1000)

        response = move([(account, event.user_account(), 100)], payment_method="boleto")

        assert_error(response, 400, "QIT000001")
        assert balance(account) == 1000

    def test_empty_transfer_list(self):
        response = payments.send(
            "POST",
            "/internal/transactions",
            json={"idempotency_key": new_key(), "payment_method": "balance", "transfers": []},
        )

        assert_error(response, 400, "QIT000001")

    def test_without_token(self):
        response = payments.send(
            "POST",
            "/internal/transactions",
            json={"idempotency_key": new_key(), "payment_method": "balance", "transfers": []},
            token=None,
        )

        assert_error(response, 403, "QIT000002")


class TestIdempotency:
    def test_same_key_and_content_replays_without_moving_again(self):
        event = Event()
        buyer = event.user_account(balance_cents=5000)
        stand = event.stand_account()
        key = new_key("purchase")

        first = move([(buyer, stand, 3000)], idempotency_key=key)
        second = move([(buyer, stand, 3000)], idempotency_key=key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json() == first.json()
        assert balance(buyer) == 2000
        assert balance(stand) == 3000

    def test_same_key_with_other_content_is_refused(self):
        event = Event()
        buyer = event.user_account(balance_cents=5000)
        stand = event.stand_account()
        key = new_key("purchase")
        setup_ok(move([(buyer, stand, 3000)], idempotency_key=key))

        response = move([(buyer, stand, 1000)], idempotency_key=key)

        assert_error(response, 409, "QIT002025")
        assert balance(buyer) == 2000

    def test_key_is_unique_across_the_whole_api_not_per_event(self):
        """A mesma chave em dois eventos é a MESMA chave: quem gera garante que
        ela é única (purchase:{id da compra})."""
        first_event = Event()
        second_event = Event()
        key = new_key("purchase")
        payer_one = first_event.user_account(balance_cents=1000)
        payer_two = second_event.user_account(balance_cents=1000)

        first = move([(payer_one, first_event.user_account(), 100)], idempotency_key=key)
        second = move([(payer_two, second_event.user_account(), 100)], idempotency_key=key)

        assert first.status_code == 201
        assert_error(second, 409, "QIT002025")
        assert balance(payer_two) == 1000

    def test_refused_request_leaves_no_trace_and_can_be_retried(self):
        event = Event()
        buyer = event.user_account(balance_cents=1000)
        stand = event.stand_account()
        key = new_key("purchase")

        refused = move([(buyer, stand, 3000)], idempotency_key=key)
        setup_ok(move([(event.external, buyer, 2000)], payment_method="cash"))
        retried = move([(buyer, stand, 3000)], idempotency_key=key)

        assert_error(refused, 409, "QIT002021")
        assert retried.status_code == 201
        assert balance(buyer) == 0
        assert balance(stand) == 3000
