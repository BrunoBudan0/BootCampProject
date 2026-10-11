"""POST /internal/accounts — a API de Eventos abre uma conta.

Quem chama é a API de Eventos; aqui o teste faz o papel dela, com o
token de Pagamentos. A conta nasce com saldo zero, e a chave de
idempotência garante que a mesma credencial ou o mesmo stand não ganhem
duas contas.

Corpo:     event_id, kind (user | fee | external), idempotency_key,
           holder_id e holder_type (attendee | company), os dois
           obrigatórios em user e proibidos em fee e external
Respostas: 201 a conta · 200 a mesma conta (mesma chave) · 400 QIT000001
           · 403 QIT000002 · 409 QIT002025 (mesma chave, outro conteúdo)
           · 409 QIT002036 (o evento já tem essa conta, com outra chave)
"""

from concurrent.futures import ThreadPoolExecutor

from tests.utils.payments import assert_error, is_uuid, new_key, new_uuid
from tests.utils.services import payments, users


def new_account(**changes):
    payload = {
        "event_id": new_uuid(),
        "holder_id": new_uuid(),
        "holder_type": "attendee",
        "kind": "user",
        "idempotency_key": new_key("account"),
    }
    payload.update(changes)
    return payload


def new_system_account(kind, **changes):
    payload = {"event_id": new_uuid(), "kind": kind, "idempotency_key": new_key("account")}
    payload.update(changes)
    return payload


def create(payload, **send_options):
    return payments.send("POST", "/internal/accounts", json=payload, **send_options)


class TestCreateAccount:
    def test_creates_user_account_with_zero_balance(self):
        payload = new_account()

        response = create(payload)

        assert response.status_code == 201
        account = response.json()
        assert is_uuid(account["id"])
        assert account["event_id"] == payload["event_id"]
        assert account["holder_id"] == payload["holder_id"]
        assert account["holder_type"] == "attendee"
        assert account["kind"] == "user"
        assert account["balance_cents"] == 0
        assert account["blocked"] is False

    def test_creates_stand_account_for_a_company(self):
        response = create(new_account(holder_type="company"))

        assert response.status_code == 201
        assert response.json()["holder_type"] == "company"

    def test_creates_system_accounts_without_holder(self):
        event_id = new_uuid()

        for kind in ("fee", "external"):
            response = create(new_system_account(kind, event_id=event_id))

            assert response.status_code == 201, f"{kind}: {response.text}"
            assert response.json()["kind"] == kind
            assert response.json()["holder_id"] is None
            assert response.json()["holder_type"] is None
            assert response.json()["balance_cents"] == 0

    def test_same_key_returns_the_same_account(self):
        payload = new_account()

        first = create(payload)
        second = create(payload)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]

    def test_different_keys_create_different_accounts(self):
        first = create(new_account())
        second = create(new_account())

        assert first.status_code == second.status_code == 201
        assert first.json()["id"] != second.json()["id"]

    def test_same_key_with_other_content_is_refused(self):
        payload = new_account()
        create(payload)

        response = create(new_account(idempotency_key=payload["idempotency_key"]))

        assert_error(response, 409, "QIT002025")

    def test_same_key_with_other_holder_type_is_refused(self):
        payload = new_account()
        create(payload)

        response = create({**payload, "holder_type": "company"})

        assert_error(response, 409, "QIT002025")


class TestOneAccountPerOwnerAndKindInEachEvent:
    def test_second_fee_account_in_the_same_event_is_refused(self):
        first = new_system_account("fee")
        create(first)

        response = create(new_system_account("fee", event_id=first["event_id"]))

        assert_error(response, 409, "QIT002036")

    def test_second_external_account_in_the_same_event_is_refused(self):
        first = new_system_account("external")
        create(first)

        response = create(new_system_account("external", event_id=first["event_id"]))

        assert_error(response, 409, "QIT002036")

    def test_same_holder_cannot_get_two_accounts_in_the_same_event(self):
        first = new_account()
        create(first)

        response = create(new_account(event_id=first["event_id"], holder_id=first["holder_id"]))

        assert_error(response, 409, "QIT002036")

    def test_same_holder_gets_one_account_in_each_event(self):
        holder_id = new_uuid()

        first = create(new_account(holder_id=holder_id))
        second = create(new_account(holder_id=holder_id))

        assert first.status_code == second.status_code == 201


class TestCreateAccountConcurrency:
    def test_parallel_requests_with_the_same_key_create_one_account(self):
        """É o único teste que passa pelo caminho do IntegrityError da conta.

        As requisições atravessam juntas a consulta prévia ("já existe conta
        com esta chave?"), todas respondem "não", e quem fecha a janela é o
        UNIQUE do banco. A que perde a corrida responde como replay (200, a
        mesma conta) — nunca 500 e nunca 409, porque o pedido é o mesmo.
        """
        payload = new_account()

        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(lambda _: create(payload), range(10)))

        statuses = [response.status_code for response in responses]
        assert statuses.count(201) == 1, statuses
        assert set(statuses) <= {200, 201}, statuses
        assert len({response.json()["id"] for response in responses}) == 1


class TestCreateAccountRefusals:
    def test_unknown_kind_is_refused(self):
        assert_error(create(new_account(kind="savings")), 400, "QIT000001")

    def test_user_account_without_holder_is_refused(self):
        payload = new_account()
        del payload["holder_id"]

        assert_error(create(payload), 400, "QIT000001")

    def test_user_account_without_holder_type_is_refused(self):
        payload = new_account()
        del payload["holder_type"]

        assert_error(create(payload), 400, "QIT000001")

    def test_unknown_holder_type_is_refused(self):
        assert_error(create(new_account(holder_type="organizer")), 400, "QIT000001")

    def test_system_account_with_holder_is_refused(self):
        assert_error(create(new_system_account("fee", holder_id=new_uuid())), 400, "QIT000001")

    def test_system_account_with_holder_type_is_refused(self):
        assert_error(create(new_system_account("external", holder_type="company")), 400, "QIT000001")

    def test_missing_event_is_refused(self):
        payload = new_account()
        del payload["event_id"]

        assert_error(create(payload), 400, "QIT000001")

    def test_event_id_must_be_uuid(self):
        assert_error(create(new_account(event_id="evento-1")), 400, "QIT000001")

    def test_unknown_field_is_refused(self):
        assert_error(create(new_account(balance_cents=1000)), 400, "QIT000001")

    def test_without_token_is_refused(self):
        assert_error(create(new_account(), token=None), 403, "QIT000002")

    def test_token_of_another_api_is_refused(self):
        assert_error(create(new_account(), token=users.token), 403, "QIT000002")
