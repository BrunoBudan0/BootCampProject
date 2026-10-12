"""GET /internal/events/{id}/reconciliation: o fechamento do evento.

Quem chama é a API de Eventos, quando o organizador pede o fechamento.
Pagamentos confere duas coisas:
  1. a soma dos saldos de todas as contas do evento é zero (a external
     negativa é o espelho do dinheiro que entrou de fora);
  2. o saldo guardado de cada conta é igual ao que o histórico de
     transações dá.

Resposta: {event_id, sum_cents, accounts: [{id, kind, holder_id,
           balance_cents, history_cents}], mismatches: [id de conta]}

O caso de divergência (saldo guardado diferente do histórico) não tem
teste black-box: para provocá-lo seria preciso escrever no banco por
fora da API. Ele existe para detectar justamente isso.
"""

from tests.utils.payments import Event, assert_error, move, new_uuid, reverse, setup_ok
from tests.utils.services import payments


class TestReconciliation:
    def test_new_event_closes_at_zero(self):
        event = Event()

        reconciliation = event.reconciliation()

        assert reconciliation["event_id"] == event.id
        assert reconciliation["sum_cents"] == 0
        assert reconciliation["mismatches"] == []
        kinds = sorted(account["kind"] for account in reconciliation["accounts"])
        assert kinds == ["external", "fee"]

    def test_purchases_transfer_and_refund_still_close_at_zero(self):
        event = Event()
        buyer = event.user_account(balance_cents=10000)
        friend = event.user_account(balance_cents=3000)
        stand = event.stand_account()
        key, purchase = event.purchase(buyer, stand)
        setup_ok(purchase)
        setup_ok(event.purchase(friend, stand, total=2000, fee=100, cashback=40)[1])
        setup_ok(move([(buyer, friend, 500)]))
        setup_ok(reverse(key))

        reconciliation = event.reconciliation()

        assert reconciliation["sum_cents"] == 0
        assert reconciliation["mismatches"] == []
        for account in reconciliation["accounts"]:
            assert account["balance_cents"] == account["history_cents"], account

    def test_external_mirrors_the_money_that_came_in(self):
        event = Event()
        event.user_account(balance_cents=10000)
        event.user_account(balance_cents=2500)

        assert event.balance_of(event.external) == -12500

    def test_lists_only_this_events_accounts(self):
        event = Event()
        mine = event.user_account()
        other_event = Event()
        other_event.user_account()

        ids = {account["id"] for account in event.reconciliation()["accounts"]}

        assert ids == {event.external["id"], event.fee["id"], mine["id"]}

    def test_unknown_event_is_empty_and_closes_at_zero(self):
        response = payments.send("GET", f"/internal/events/{new_uuid()}/reconciliation")

        assert response.status_code == 200
        assert response.json()["sum_cents"] == 0
        assert response.json()["accounts"] == []

    def test_without_token(self):
        response = payments.send("GET", f"/internal/events/{new_uuid()}/reconciliation", token=None)

        assert_error(response, 403, "QIT000002")
