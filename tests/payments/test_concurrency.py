"""O principal desafio da RFC: muitas requisições ao mesmo tempo.

Dois aparelhos logados na mesma credencial, ou o app reenviando porque a
conexão caiu. Com o desenho ingênuo (ler o saldo, decidir, gravar), as
requisições leem o mesmo saldo antes de qualquer escrita e todas passam.

Estes testes disparam as requisições em paralelo, com threads, e
conferem o resultado final. Eles só ficam verdes de verdade com o
débito condicional (UPDATE ... WHERE balance_cents >= :valor) e com o
UNIQUE (idempotency_key, leg) no banco.
"""

from concurrent.futures import ThreadPoolExecutor

from tests.utils.payments import Event, balance, move, new_key

PARALLEL_REQUESTS = 10


def fire_together(function, times):
    with ThreadPoolExecutor(max_workers=times) as pool:
        futures = [pool.submit(function) for _ in range(times)]
        return [future.result() for future in futures]


class TestConcurrency:
    def test_parallel_debits_never_overdraw(self):
        """Saldo para 2 compras de R$ 40, e 10 chegando juntas: exatamente 2 passam."""
        event = Event()
        buyer = event.user_account(balance_cents=10000)
        company = event.user_account()

        responses = fire_together(lambda: move([(buyer, company, 4000)]), PARALLEL_REQUESTS)

        statuses = sorted(response.status_code for response in responses)
        assert statuses.count(201) == 2, statuses
        assert statuses.count(409) == PARALLEL_REQUESTS - 2, statuses
        for response in responses:
            if response.status_code == 409:
                assert response.json()["code"] == "QIT002021"

        assert balance(buyer) == 2000
        assert balance(company) == 8000
        assert event.reconciliation()["sum_cents"] == 0

    def test_parallel_requests_with_the_same_key_move_money_once(self):
        """O app reenviou a mesma compra várias vezes ao mesmo tempo.

        Exatamente uma executa. As outras recebem 200 (a mesma resposta) ou
        409 (o UNIQUE barrou a corrida) — mas nenhuma cobra de novo.
        """
        event = Event()
        buyer = event.user_account(balance_cents=10000)
        company = event.user_account()
        key = new_key("purchase")

        responses = fire_together(lambda: move([(buyer, company, 3000)], idempotency_key=key), PARALLEL_REQUESTS)

        statuses = [response.status_code for response in responses]
        assert statuses.count(201) == 1, statuses
        assert set(statuses) <= {200, 201, 409}, statuses
        assert balance(buyer) == 7000
        assert balance(company) == 3000
