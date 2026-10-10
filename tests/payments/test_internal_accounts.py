"""POST /internal/accounts — a API de Eventos abre uma conta.

Quem chama é a API de Eventos; aqui o teste faz o papel dela, com o
token de Pagamentos. A conta nasce com saldo zero, e a chave de
idempotência garante que a mesma credencial ou o mesmo stand não ganhem
duas contas.

Corpo:     event_id, kind (user | fee | external), holder_id (obrigatório
           em user, proibido em fee e external), idempotency_key
Respostas: 201 a conta · 200 a mesma conta (mesma chave) · 400 QIT000001
           · 403 QIT000002 · 409 QIT002025 (mesma chave, outro conteúdo)
"""

from concurrent.futures import ThreadPoolExecutor

from tests.utils.payments import assert_error, is_uuid, new_key, new_uuid
from tests.utils.services import payments, users


def new_account(**changes):
    """Um pedido válido, com UUIDs novos: cada teste vive no próprio mundo."""
    payload = {
        "event_id": new_uuid(),
        "holder_id": new_uuid(),
        "kind": "user",
        "idempotency_key": new_key("account"),
    }
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
        assert is_uuid(account["id"])  # R5: nunca o número do banco
        assert account["event_id"] == payload["event_id"]
        assert account["holder_id"] == payload["holder_id"]
        assert account["kind"] == "user"
        assert account["balance_cents"] == 0
        assert account["blocked"] is False

    def test_creates_system_accounts_without_holder(self):
        event_id = new_uuid()

        for kind in ("fee", "external"):
            payload = new_account(event_id=event_id, kind=kind)
            del payload["holder_id"]

            response = create(payload)

            assert response.status_code == 201, f"{kind}: {response.text}"
            assert response.json()["kind"] == kind
            assert response.json()["holder_id"] is None
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


class TestCreateAccountConcurrency:
    def test_parallel_requests_with_the_same_key_create_one_account(self):
        """A API de Eventos reenviou o mesmo pedido várias vezes ao mesmo tempo.

        É o único teste que passa pelo caminho do IntegrityError: as
        requisições atravessam juntas a consulta prévia ("já existe conta
        com esta chave?"), todas respondem "não", e quem fecha a janela é o
        UNIQUE do banco. A que perde a corrida tem de responder como replay
        (200, a mesma conta) — nunca 500 e nunca 409, porque o pedido é o
        mesmo.
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

    def test_system_account_with_holder_is_refused(self):
        assert_error(create(new_account(kind="fee")), 400, "QIT000001")

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
