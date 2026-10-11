"""O principal desafio da RFC: muitas requisições ao mesmo tempo.

Dois aparelhos logados na mesma credencial, ou o app reenviando porque a
conexão caiu. Com o desenho ingênuo (ler o saldo, decidir, gravar), as
requisições leem o mesmo saldo antes de qualquer escrita e todas passam.

Estes testes disparam as requisições em paralelo, com threads, e
conferem o resultado final. Eles só ficam verdes de verdade com o
débito condicional (UPDATE ... WHERE balance_cents >= :valor) e com o
UNIQUE (idempotency_key, leg) no banco, gravado ANTES de mexer no saldo.
"""

from tests.utils.payments import Event, balance, fire_together, move, new_key, new_uuid, transfer

PARALLEL_REQUESTS = 10


class TestConcurrency:
    def test_parallel_debits_never_overdraw(self):
        """Saldo para 2 compras de R$ 40, e 10 chegando juntas: exatamente 2 passam."""
        event = Event()
        buyer = event.user_account(balance_cents=10000)
        stand = event.stand_account()

        responses = fire_together(lambda: move([(buyer, stand, 4000)]), PARALLEL_REQUESTS)

        statuses = sorted(response.status_code for response in responses)
        assert statuses.count(201) == 2, statuses
        assert statuses.count(409) == PARALLEL_REQUESTS - 2, statuses
        for response in responses:
            if response.status_code == 409:
                assert response.json()["code"] == "QIT002021"

        assert balance(buyer) == 2000
        assert balance(stand) == 8000
        assert event.reconciliation()["sum_cents"] == 0

    def test_parallel_requests_with_the_same_key_move_money_once(self):
        """O app reenviou a mesma compra várias vezes ao mesmo tempo, e o saldo
        só cobre uma. Quem chega depois recebe a mesma resposta (200), e não
        um "saldo insuficiente" que faria Eventos cancelar uma compra paga."""
        event = Event()
        buyer = event.user_account(balance_cents=3000)
        stand = event.stand_account()
        key = new_key("purchase")

        responses = fire_together(lambda: move([(buyer, stand, 3000)], idempotency_key=key), PARALLEL_REQUESTS)

        statuses = [response.status_code for response in responses]
        assert statuses.count(201) == 1, statuses
        assert statuses.count(200) == PARALLEL_REQUESTS - 1, [response.text for response in responses]
        assert balance(buyer) == 0
        assert balance(stand) == 3000

    def test_parallel_transfers_with_the_same_key_move_money_once(self):
        event = Event()
        source = event.user_account(balance_cents=1500)
        destination = event.user_account()
        key = new_uuid()

        responses = fire_together(
            lambda: transfer(source, destination, 1500, idempotency_key=key), PARALLEL_REQUESTS
        )

        statuses = [response.status_code for response in responses]
        assert statuses.count(201) == 1, statuses
        assert statuses.count(200) == PARALLEL_REQUESTS - 1, [response.text for response in responses]
        assert len({response.json()["id"] for response in responses}) == 1
        assert balance(source) == 0
        assert balance(destination) == 1500
