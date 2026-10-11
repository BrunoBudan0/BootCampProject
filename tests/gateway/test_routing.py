import uuid

from tests.gateway.helpers import User
from tests.utils.services import gateway


class TestRouting:
    def test_internal_routes_are_not_exposed(self):
        user = User("organizer")

        for method, path in (("POST", "/internal/login"), ("GET", f"/internal/companies/{uuid.uuid4()}"),
                             ("POST", "/internal/transactions")):
            response = user.send(method, path, json={})
            assert response.status_code == 404, path
            assert response.json()["code"] == "QIT000404"

    def test_request_id_comes_back(self):
        user = User("attendee")

        response = user.send("GET", "/me", headers={"X-Request-ID": "teste-gateway-123"})

        assert response.headers["X-Request-ID"] == "teste-gateway-123"

    def test_query_string_reaches_the_api(self):
        organizer = User("organizer")

        response = organizer.send("GET", "/events", params={"limit": "0"})

        assert response.status_code == 400
        assert response.json()["code"] == "QIT000001"

    def test_pix_webhook_passes_without_token_and_without_session(self):
        response = gateway.send(
            "PUT", f"/webhooks/pix/{uuid.uuid4()}", token=None,
            data=b'{"status": "paid", "amount_cents": 100, "reference": "x"}',
            headers={"Content-Type": "application/json", "X-Pix-Signature": "assinatura-falsa"},
        )

        # quem recusa é Pagamentos, pela assinatura: a porta do Gateway abriu
        assert response.status_code in (400, 401)

    def test_app_without_internal_token_is_refused(self):
        response = gateway.send("GET", "/me", token=None)

        assert response.status_code == 403
        assert response.json()["code"] == "QIT000002"
