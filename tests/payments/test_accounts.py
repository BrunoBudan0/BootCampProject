"""GET /accounts e GET /accounts/{id}: o dono consulta as contas e o saldo.

Rotas públicas: chegam pelo Gateway, que diz quem chama em X-User-Id.
Pagamentos confere sozinha que a conta é de quem chama (holder_id).

Conta que não é sua responde 404 QIT002020, igual à conta que não existe
(R8): quem varre ids não aprende quais existem.
"""

from tests.utils.payments import Event, as_caller, assert_error, get_account, new_uuid, same_refusal
from tests.utils.services import payments


class TestGetAccount:
    def test_holder_sees_own_account_and_balance(self):
        event = Event()
        account = event.user_account(balance_cents=5000)

        response = get_account(account)

        assert response.status_code == 200
        assert response.json()["id"] == account["id"]
        assert response.json()["balance_cents"] == 5000

    def test_new_account_starts_at_zero(self):
        account = Event().user_account()

        response = get_account(account)

        assert response.status_code == 200
        assert response.json()["balance_cents"] == 0

    def test_account_of_someone_else_is_not_found(self):
        account = Event().user_account(balance_cents=5000)

        response = get_account(account, caller=new_uuid())

        assert_error(response, 404, "QIT002020")

    def test_missing_account_is_not_found(self):
        response = get_account({"id": new_uuid()}, caller=new_uuid())

        assert_error(response, 404, "QIT002020")

    def test_someone_elses_and_missing_look_the_same(self):
        stranger = new_uuid()
        account = Event().user_account()

        someone_elses = get_account(account, caller=stranger)
        missing = get_account({"id": new_uuid()}, caller=stranger)

        assert same_refusal(someone_elses, missing)

    def test_malformed_id_is_not_found_instead_of_crashing(self):
        response = get_account({"id": "not-a-uuid"}, caller=new_uuid())

        assert_error(response, 404, "QIT002020")

    def test_request_without_caller_sees_no_user_account(self):
        account = Event().user_account()

        response = payments.send("GET", f"/accounts/{account['id']}")

        assert_error(response, 404, "QIT002020")

    def test_request_without_caller_cannot_reach_system_account(self):
        event = Event()

        response = payments.send("GET", f"/accounts/{event.fee['id']}")

        assert_error(response, 404, "QIT002020")

    def test_system_accounts_belong_to_nobody(self):
        event = Event()

        response = get_account(event.fee, caller=new_uuid())

        assert_error(response, 404, "QIT002020")


class TestListAccounts:
    def test_lists_only_the_callers_accounts(self):
        holder = new_uuid()
        mine_in_one_event = Event().user_account(holder_id=holder)
        mine_in_another_event = Event().user_account(holder_id=holder)
        Event().user_account()

        response = payments.send("GET", "/accounts", headers=as_caller(holder))

        assert response.status_code == 200
        ids = {account["id"] for account in response.json()["data"]}
        assert ids == {mine_in_one_event["id"], mine_in_another_event["id"]}

    def test_caller_without_accounts_gets_an_empty_list(self):
        response = payments.send("GET", "/accounts", headers=as_caller(new_uuid()))

        assert response.status_code == 200
        assert response.json()["data"] == []
