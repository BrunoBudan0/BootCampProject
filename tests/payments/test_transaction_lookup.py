"""GET /transactions/{id} — uma transação: origem, destino, valor, método e status.

Rota pública, pelo Gateway. Quem enxerga: o dono da conta de origem ou o
da conta de destino. Os outros recebem 404 QIT002023, igual à transação
que não existe (R8).
"""

from tests.utils.payments import Event, assert_error, get_transaction, move, new_uuid, same_refusal


def a_payment():
    event = Event()
    payer = event.user_account(balance_cents=5000)
    receiver = event.user_account()
    response = move([(payer, receiver, 1500)])
    assert response.status_code == 201, f"A PREPARAÇÃO (o pagamento) falhou: {response.text}"

    return payer, receiver, response.json()["transactions"][0]


class TestTransactionLookup:
    def test_payer_sees_the_transaction(self):
        payer, receiver, transaction = a_payment()

        response = get_transaction(transaction["id"], caller=payer["holder_id"])

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == transaction["id"]
        assert body["source_account_id"] == payer["id"]
        assert body["destination_account_id"] == receiver["id"]
        assert body["amount_cents"] == 1500
        assert body["payment_method"] == "balance"
        assert body["status"] == "settled"

    def test_receiver_sees_the_transaction(self):
        _, receiver, transaction = a_payment()

        response = get_transaction(transaction["id"], caller=receiver["holder_id"])

        assert response.status_code == 200

    def test_stranger_does_not_see_it(self):
        _, _, transaction = a_payment()

        assert_error(get_transaction(transaction["id"], caller=new_uuid()), 404, "QIT002023")

    def test_missing_transaction(self):
        assert_error(get_transaction(new_uuid(), caller=new_uuid()), 404, "QIT002023")

    def test_strangers_and_missing_look_the_same(self):
        _, _, transaction = a_payment()
        stranger = new_uuid()

        assert same_refusal(
            get_transaction(transaction["id"], caller=stranger),
            get_transaction(new_uuid(), caller=stranger),
        )
