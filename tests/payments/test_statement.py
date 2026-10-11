"""GET /accounts/{id}/statement — o extrato paginado.

Não existe tabela de lançamentos: o extrato são as transações em que a
conta aparece como origem ou destino, já settled ou reversed, da mais
nova para a mais antiga, com o saldo depois de cada uma calculado na
própria consulta.

A ordem é a do momento em que o dinheiro andou (settled_at), e não a do
pedido (created_at): um Pix pedido antes de uma transferência e pago
depois dela entra no extrato depois dela, e o saldo das linhas antigas
nunca muda.

Parâmetros: limit (1 a 100, padrão 10), page (padrão 0), date_from,
            date_to (data, ou data e hora ISO). Data sem hora é o dia em
            America/Sao_Paulo, e date_to só com a data inclui o dia
            inteiro. date_from depois de date_to é 400. Qualquer outro
            nome é 400.
Linha:      {transaction_id, payment_method, status, amount_cents,
             balance_after_cents, created_at, settled_at}
            amount_cents tem SINAL: positivo entrou, negativo saiu.
Envelope:   {data, limit, page, is_last_page}
"""

from datetime import datetime, timedelta, timezone

import pytest

from tests.utils import mockserver
from tests.utils.mockserver import PIX_CHARGES, pix_charge_answer
from tests.utils.payments import (
    Event,
    assert_error,
    move,
    new_key,
    new_uuid,
    pix_webhook,
    recharge,
    reverse,
    statement,
    transfer,
)

SAO_PAULO_OFFSET = timezone(timedelta(hours=-3))


def today_in_sao_paulo():
    return datetime.now(SAO_PAULO_OFFSET).date()


@pytest.fixture
def pix_provider():
    mockserver.reset()
    mockserver.expect("POST", PIX_CHARGES, 201, pix_charge_answer())
    yield
    mockserver.reset()


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
        stand = event.stand_account()
        key = new_key("purchase")
        move([(account, stand, 4000)], idempotency_key=key)
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

    def test_a_pix_paid_late_does_not_rewrite_past_lines(self, pix_provider):
        event = Event()
        account = event.user_account(balance_cents=5000)
        pix = recharge(account, "pix", 1000).json()
        transfer(account, event.user_account(), 5000)
        pix_webhook(pix["id"], "paid", 1000)

        lines = statement(account).json()["data"]

        assert [line["amount_cents"] for line in lines] == [1000, -5000, 5000]
        assert [line["balance_after_cents"] for line in lines] == [1000, 0, 5000]
        assert lines[0]["transaction_id"] == pix["id"]
        assert datetime.fromisoformat(lines[0]["settled_at"]) > datetime.fromisoformat(lines[1]["settled_at"])

    def test_date_to_with_only_the_date_includes_the_whole_day(self):
        account = Event().user_account(balance_cents=1000)

        response = statement(account, date_to=today_in_sao_paulo().isoformat())

        assert len(response.json()["data"]) == 1

    def test_date_from_with_only_the_date_starts_at_midnight_in_sao_paulo(self):
        account = Event().user_account(balance_cents=1000)

        response = statement(account, date_from=today_in_sao_paulo().isoformat())

        assert len(response.json()["data"]) == 1

    def test_a_day_that_already_ended_leaves_today_out(self):
        account = Event().user_account(balance_cents=1000)
        yesterday = today_in_sao_paulo() - timedelta(days=1)

        response = statement(account, date_to=yesterday.isoformat())

        assert response.json()["data"] == []

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

    def test_limit_zero(self):
        """Uma página de zero linhas nunca é a última: quem pagina entraria em laço."""
        assert_error(statement(Event().user_account(), limit=0), 400, "QIT000001")

    def test_date_from_after_date_to(self):
        today = today_in_sao_paulo()
        yesterday = today - timedelta(days=1)

        response = statement(Event().user_account(), date_from=today.isoformat(), date_to=yesterday.isoformat())

        assert_error(response, 400, "QIT000001")

    def test_unknown_parameter(self):
        """Sem isto, um ?limt=5 com a letra trocada devolveria a página padrão
        como se o filtro tivesse funcionado."""
        assert_error(statement(Event().user_account(), limt=5), 400, "QIT000001")

    def test_page_must_be_a_number(self):
        assert_error(statement(Event().user_account(), page="first"), 400, "QIT000001")
