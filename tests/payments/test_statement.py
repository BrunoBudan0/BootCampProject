"""GET /accounts/{id}/statement — o extrato paginado.

Não existe tabela de lançamentos: o extrato são as transações em que a
conta aparece como origem ou destino, já settled ou reversed, da mais
nova para a mais antiga, com o saldo depois de cada uma calculado na
própria consulta.

Parâmetros: limit (padrão 10, teto 100), page (padrão 0), date_from,
            date_to (data e hora ISO). Qualquer outro nome é 400.
Linha:      {transaction_id, payment_method, status, amount_cents,
             balance_after_cents, created_at}
            amount_cents tem SINAL: positivo entrou, negativo saiu.
Envelope:   {data, limit, page, is_last_page}
"""

from datetime import datetime, timedelta, timezone

from tests.utils.payments import Event, assert_error, move, new_key, new_uuid, reverse, statement


class TestStatement:
    def test_each_line_carries_the_balance_after_it(self):
        event = Event()
        account = event.user_account(balance_cents=5000)
        move([(account, event.user_account(), 1500)])

        response = statement(account)

        assert response.status_code == 200
        lines = response.json()["data"]
        assert [line["amount_cents"] for line in lines] == [-1500, 5000]
        assert [line["balance_after_cents"] for line in lines] == [3500, 5000]
        assert lines[0]["payment_method"] == "balance"
        assert lines[1]["payment_method"] == "cash"

    def test_reversed_purchase_stays_next_to_its_refund(self):
        """R4 visto pelo cliente: a compra continua no extrato, ao lado da devolução."""
        event = Event()
        account = event.user_account(balance_cents=5000)
        company = event.user_account()
        key = new_key("purchase")
        move([(account, company, 4000)], idempotency_key=key)
        reverse(key)

        lines = statement(account).json()["data"]

        assert [line["amount_cents"] for line in lines] == [4000, -4000, 5000]
        assert [line["status"] for line in lines] == ["settled", "reversed", "settled"]
        assert [line["balance_after_cents"] for line in lines] == [5000, 1000, 5000]

    def test_pages_say_if_there_is_more_and_never_repeat(self):
        event = Event()
        account = event.user_account(balance_cents=3000)
        receiver = event.user_account()
        move([(account, receiver, 1000)])
        move([(account, receiver, 1000)])

        first = statement(account, limit=2, page=0).json()
        second = statement(account, limit=2, page=1).json()

        assert len(first["data"]) == 2
        assert first["is_last_page"] is False
        assert first["limit"] == 2
        assert first["page"] == 0
        assert len(second["data"]) == 1
        assert second["is_last_page"] is True
        first_ids = {line["transaction_id"] for line in first["data"]}
        second_ids = {line["transaction_id"] for line in second["data"]}
        assert first_ids.isdisjoint(second_ids)

    def test_date_range_filters_the_lines(self):
        account = Event().user_account(balance_cents=1000)
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        assert statement(account, date_from=tomorrow).json()["data"] == []
        assert len(statement(account, date_from=yesterday).json()["data"]) == 1

    def test_new_account_has_an_empty_statement(self):
        response = statement(Event().user_account())

        assert response.status_code == 200
        assert response.json()["data"] == []
        assert response.json()["is_last_page"] is True


class TestStatementRefusals:
    def test_statement_of_someone_else(self):
        account = Event().user_account(balance_cents=1000)

        assert_error(statement(account, caller=new_uuid()), 404, "QIT002020")

    def test_limit_above_the_ceiling(self):
        assert_error(statement(Event().user_account(), limit=101), 400, "QIT000001")

    def test_unknown_parameter(self):
        """Sem isto, um ?limt=5 com a letra trocada devolveria a página padrão
        como se o filtro tivesse funcionado."""
        assert_error(statement(Event().user_account(), limt=5), 400, "QIT000001")

    def test_page_must_be_a_number(self):
        assert_error(statement(Event().user_account(), page="first"), 400, "QIT000001")
