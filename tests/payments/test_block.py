"""PUT /internal/accounts/{id}/block — bloquear ou liberar uma conta.

A API de Eventos chama junto com o bloqueio da credencial (crachá
perdido). Conta bloqueada não paga nem recebe. A rota é idempotente:
bloquear duas vezes dá o mesmo resultado.

Corpo:     {"blocked": true | false}
Respostas: 200 a conta · 400 QIT000001 · 404 QIT002020
"""

from tests.utils.payments import Event, assert_error, balance, block, move, new_uuid, setup_ok
from tests.utils.services import payments


class TestBlock:
    def test_blocks_the_account(self):
        account = Event().user_account()

        response = block(account)

        assert response.status_code == 200
        assert response.json()["id"] == account["id"]
        assert response.json()["blocked"] is True

    def test_blocking_twice_gives_the_same_result(self):
        account = Event().user_account()

        setup_ok(block(account))
        response = block(account)

        assert response.status_code == 200
        assert response.json()["blocked"] is True

    def test_unblocks_the_account(self):
        account = Event().user_account()
        setup_ok(block(account))

        response = block(account, blocked=False)

        assert response.status_code == 200
        assert response.json()["blocked"] is False

    def test_blocked_account_cannot_pay(self):
        event = Event()
        account = event.user_account(balance_cents=5000)
        stand = event.stand_account()
        setup_ok(block(account))

        response = move([(account, stand, 1000)])

        assert_error(response, 409, "QIT002022")
        assert balance(account) == 5000
        assert balance(stand) == 0

    def test_blocked_account_cannot_receive(self):
        event = Event()
        payer = event.user_account(balance_cents=5000)
        blocked = event.user_account()
        setup_ok(block(blocked))

        response = move([(payer, blocked, 1000)])

        assert_error(response, 409, "QIT002022")
        assert balance(payer) == 5000
        assert balance(blocked) == 0

    def test_unblocked_account_pays_again(self):
        event = Event()
        account = event.user_account(balance_cents=5000)
        stand = event.stand_account()
        setup_ok(block(account))
        setup_ok(block(account, blocked=False))

        response = move([(account, stand, 1000)])

        assert response.status_code == 201
        assert balance(account) == 4000


class TestBlockRefusals:
    def test_missing_account_is_not_found(self):
        assert_error(block({"id": new_uuid()}), 404, "QIT002020")

    def test_body_without_blocked_is_refused(self):
        account = Event().user_account()

        response = payments.send("PUT", f"/internal/accounts/{account['id']}/block", json={})

        assert_error(response, 400, "QIT000001")

    def test_blocked_must_be_boolean(self):
        account = Event().user_account()

        response = payments.send("PUT", f"/internal/accounts/{account['id']}/block", json={"blocked": "yes"})

        assert_error(response, 400, "QIT000001")

    def test_without_token_is_refused(self):
        account = Event().user_account()

        response = payments.send(
            "PUT", f"/internal/accounts/{account['id']}/block", json={"blocked": True}, token=None
        )

        assert_error(response, 403, "QIT000002")
