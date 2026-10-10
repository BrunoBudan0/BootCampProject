import uuid

from tests.events.helpers import create_company, create_event, create_stand, headers
from tests.utils.services import events


# precisa de Usuários (POST /companies, GET /internal/companies/{id})
# e de Pagamentos (POST /internal/accounts) de pé

class TestAddCompany:
    def test_organizer_adds_stand(self):
        organizer = uuid.uuid4()
        event_id = create_event(organizer)
        company_id = create_company()

        response = events.send(
            "POST", f"/events/{event_id}/companies",
            json={"company_id": company_id, "stand_name": "Livraria A"},
            headers=headers("organizer", organizer),
        )

        assert response.status_code == 201
        assert response.json()["stand_name"] == "Livraria A"
        assert response.json()["account_id"]

    def test_company_only_once_per_event(self):
        organizer = uuid.uuid4()
        event_id = create_event(organizer)
        company_id = create_company()
        create_stand(organizer, event_id, company_id)

        response = events.send(
            "POST", f"/events/{event_id}/companies",
            json={"company_id": company_id, "stand_name": "De novo"},
            headers=headers("organizer", organizer),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002012"

    def test_unknown_company(self):
        organizer = uuid.uuid4()
        event_id = create_event(organizer)

        response = events.send(
            "POST", f"/events/{event_id}/companies",
            json={"company_id": str(uuid.uuid4()), "stand_name": "Fantasma"},
            headers=headers("organizer", organizer),
        )

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002009"

    def test_other_organizer_cannot_add(self):
        event_id = create_event(uuid.uuid4())

        response = events.send(
            "POST", f"/events/{event_id}/companies",
            json={"company_id": str(uuid.uuid4()), "stand_name": "Intruso"},
            headers=headers("organizer"),
        )

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002010"


class TestAddAttendee:
    def test_attendee_gets_credential(self):
        event_id = create_event(uuid.uuid4())

        response = events.send("POST", f"/events/{event_id}/attendees", headers=headers("attendee"))

        assert response.status_code == 201
        assert response.json()["blocked"] is False
        assert response.json()["account_id"]

    def test_one_credential_per_event(self):
        event_id = create_event(uuid.uuid4())
        attendee = uuid.uuid4()
        events.send("POST", f"/events/{event_id}/attendees", headers=headers("attendee", attendee))

        response = events.send("POST", f"/events/{event_id}/attendees", headers=headers("attendee", attendee))

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002013"

    def test_only_attendee_takes_credential(self):
        event_id = create_event(uuid.uuid4())

        response = events.send("POST", f"/events/{event_id}/attendees", headers=headers("organizer"))

        assert response.status_code == 403
        assert response.json()["code"] == "QIT002004"