"""POST /internal/reversals — o estorno de uma compra.

Desfazer é um fato NOVO (R4): cada transação original ganha uma
transação no sentido contrário, que aponta para ela em
reverses_transaction_id, e a original passa a `reversed`. Nada é
apagado. A ordem é fixa: primeiro as que saem de contas do sistema; por
isso o reembolso chega antes de o cashback voltar, e um cashback já
gasto sai do próprio reembolso.

O estorno é a exceção ao bloqueio: ele devolve o dinheiro mesmo que
alguma das contas esteja bloqueada.

Corpo:     original_idempotency_key, idempotency_key
Respostas: 201 {idempotency_key, transactions} · 200 replay
           · 404 QIT002023 chave original desconhecida
           · 409 QIT002026 já estornada · 409 QIT002021 sem saldo para devolver
"""

from tests.utils.payments import (
    Event,
    assert_error,
    balance,
    block,
    fire_together,
    get_transaction,
    move,
    new_key,
    new_uuid,
    reverse,
)
from tests.utils.services import payments

PARALLEL_REQUESTS = 10


def bought(event, balance_cents=5000):
    """Um comprador com saldo, uma empresa, e uma compra de R$ 40 já feita."""
    buyer = event.user_account(balance_cents=balance_cents)
    stand = event.stand_account()
    key, response = event.purchase(buyer, stand, total=4000, fee=200, cashback=80)
    assert response.status_code == 201, f"A PREPARAÇÃO (a compra) falhou: {response.text}"

    return buyer, stand, key, response.json()["transactions"]


class TestReversal:
    def test_refund_puts_everything_back(self):
        event = Event()
        buyer, stand, key, _ = bought(event)

        response = reverse(key)

        assert response.status_code == 201
        assert balance(buyer) == 5000
        assert balance(stand) == 0
        assert event.balance_of(event.fee) == 0
        assert event.reconciliation()["sum_cents"] == 0

    def test_each_reversal_points_to_its_original(self):
        event = Event()
        _, _, key, originals = bought(event)

        reversals = reverse(key).json()["transactions"]

        by_id = {original["id"]: original for original in originals}
        assert len(reversals) == len(originals)
        for reversal in reversals:
            original = by_id[reversal["reverses_transaction_id"]]
            assert reversal["source_account_id"] == original["destination_account_id"]
            assert reversal["destination_account_id"] == original["source_account_id"]
            assert reversal["amount_cents"] == original["amount_cents"]
            assert reversal["status"] == "settled"

    def test_reversal_starts_with_the_system_accounts(self):
        """fee devolve a tarifa à empresa, a empresa devolve ao público, e só
        então o público devolve o cashback."""
        event = Event()
        buyer, stand, key, _ = bought(event)

        reversals = reverse(key).json()["transactions"]

        sources = [reversal["source_account_id"] for reversal in reversals]
        assert sources == [event.fee["id"], stand["id"], buyer["id"]]

    def test_originals_become_reversed_and_stay_in_history(self):
        event = Event()
        buyer, _, key, originals = bought(event)

        reverse(key)

        response = get_transaction(originals[0]["id"], caller=buyer["holder_id"])
        assert response.status_code == 200
        assert response.json()["status"] == "reversed"

    def test_spent_cashback_comes_out_of_the_refund(self):
        """O caso da RFC: o público gastou os R$ 0,80 de cashback antes de devolver.

        Ele recebe R$ 40,00 de volta, devolve os R$ 0,80, e fica com R$ 39,20
        — ninguém fica negativo e a soma do evento continua zero.
        """
        event = Event()
        buyer, stand, key, _ = bought(event, balance_cents=4000)
        friend = event.user_account()
        move([(buyer, friend, 80)])
        assert balance(buyer) == 0

        response = reverse(key)

        assert response.status_code == 201
        assert balance(buyer) == 3920
        assert balance(stand) == 0
        assert event.reconciliation()["sum_cents"] == 0

    def test_same_reversal_key_replays_without_moving_again(self):
        event = Event()
        buyer, _, key, _ = bought(event)
        refund_key = new_key("refund")

        first = reverse(key, idempotency_key=refund_key)
        second = reverse(key, idempotency_key=refund_key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json() == first.json()
        assert balance(buyer) == 5000

    def test_refund_reaches_a_blocked_buyer(self):
        event = Event()
        buyer, stand, key, _ = bought(event)
        block(buyer)

        response = reverse(key)

        assert response.status_code == 201
        assert balance(buyer) == 5000
        assert balance(stand) == 0


class TestParallelReversals:
    def test_same_key_in_parallel_reverses_once(self):
        event = Event()
        buyer, stand, key, _ = bought(event)
        refund_key = new_key("refund")

        responses = fire_together(lambda: reverse(key, idempotency_key=refund_key), PARALLEL_REQUESTS)

        statuses = [response.status_code for response in responses]
        assert statuses.count(201) == 1, statuses
        assert statuses.count(200) == PARALLEL_REQUESTS - 1, [response.text for response in responses]
        assert balance(buyer) == 5000
        assert balance(stand) == 0
        assert event.balance_of(event.fee) == 0

    def test_different_keys_in_parallel_reverse_once(self):
        event = Event()
        buyer, stand, key, _ = bought(event)

        responses = fire_together(lambda: reverse(key), PARALLEL_REQUESTS)

        statuses = [response.status_code for response in responses]
        assert statuses.count(201) == 1, statuses
        for response in responses:
            if response.status_code != 201:
                assert_error(response, 409, "QIT002026")
        assert balance(buyer) == 5000
        assert balance(stand) == 0
        assert event.reconciliation()["sum_cents"] == 0


class TestReversalRefusals:
    def test_cannot_reverse_twice(self):
        event = Event()
        buyer, _, key, _ = bought(event)
        reverse(key)

        response = reverse(key)

        assert_error(response, 409, "QIT002026")
        assert balance(buyer) == 5000

    def test_stand_without_balance_blocks_the_refund(self):
        event = Event()
        buyer, stand, key, originals = bought(event)
        elsewhere = event.user_account()
        move([(stand, elsewhere, 3800)])

        response = reverse(key)

        assert_error(response, 409, "QIT002021")
        assert balance(buyer) == 1080
        assert balance(stand) == 0
        assert event.balance_of(event.fee) == 120
        original = get_transaction(originals[0]["id"], caller=buyer["holder_id"]).json()
        assert original["status"] == "settled"

    def test_unknown_original_key(self):
        assert_error(reverse(new_key("purchase")), 404, "QIT002023")

    def test_body_without_original_key(self):
        response = payments.send("POST", "/internal/reversals", json={"idempotency_key": new_uuid()})

        assert_error(response, 400, "QIT000001")
