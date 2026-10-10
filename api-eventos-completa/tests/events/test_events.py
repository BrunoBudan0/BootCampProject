import uuid

from tests.utils.services import events


def organizer_headers(user_id=None):
    return {"X-User-Id": user_id or str(uuid.uuid4()), "X-User-Type": "organizer"}


def new_event_body(**changes):
    body = {
        "name": "Bienal do Livro",
        "location": "São Paulo",
        "fee_rate_bps": 500,
        "cashback_rate_bps": 200,
    }
    body.update(changes)
    return body


class TestCreateEvent:
    # precisa do POST /internal/accounts de Pagamentos funcionando
    def test_creates_event_with_initial_rates(self):
        response = events.send("POST", "/events", json=new_event_body(), headers=organizer_headers())

        assert response.status_code == 201
        body = response.json()
        assert body["fee_rate_bps"] == 500
        assert body["cashback_rate_bps"] == 200

        found = events.send("GET", f"/events/{body['id']}", headers=organizer_headers())
        assert found.status_code == 200
        assert found.json()["name"] == "Bienal do Livro"

    def test_only_organizer_creates(self):
        headers = {"X-User-Id": str(uuid.uuid4()), "X-User-Type": "attendee"}
        response = events.send("POST", "/events", json=new_event_body(), headers=headers)

        assert response.status_code == 403
        assert response.json()["code"] == "QIT002004"

    def test_cashback_cannot_be_above_fee(self):
        response = events.send(
            "POST", "/events", json=new_event_body(cashback_rate_bps=900), headers=organizer_headers()
        )

        assert response.status_code == 422
        assert response.json()["code"] == "QIT002032"

    def test_rejects_unknown_field(self):
        response = events.send(
            "POST", "/events", json=new_event_body(balance=100), headers=organizer_headers()
        )

        assert response.status_code == 400
        assert response.json()["code"] == "QIT000001"


class TestGetEvent:
    def test_unknown_event_is_404(self):
        response = events.send("GET", f"/events/{uuid.uuid4()}", headers=organizer_headers())

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002010"

    def test_list_is_paginated(self):
        response = events.send("GET", "/events?limit=1&page=1", headers=organizer_headers())

        assert response.status_code == 200
        assert "data" in response.json()
        assert "is_last_page" in response.json()
