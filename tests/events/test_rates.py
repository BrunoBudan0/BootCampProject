import uuid

from tests.events.helpers import create_event, headers
from tests.utils.services import events


def change(kind, event_id, organizer, rate_bps, reason="Ajuste da organização"):
    return events.send(
        "PUT", f"/events/{event_id}/{kind}",
        json={"rate_bps": rate_bps, "reason": reason},
        headers=headers("organizer", organizer),
    )


class TestChangeRates:
    def test_new_fee_version_becomes_current(self):
        organizer = uuid.uuid4()
        event_id = create_event(organizer, fee_rate_bps=500, cashback_rate_bps=200)

        response = change("fee-rate", event_id, organizer, 700)

        assert response.status_code == 201
        assert response.json()["rate_bps"] == 700
        event = events.send("GET", f"/events/{event_id}", headers=headers("organizer", organizer)).json()
        assert event["fee_rate_bps"] == 700

    def test_cashback_cannot_go_above_fee(self):
        organizer = uuid.uuid4()
        event_id = create_event(organizer, fee_rate_bps=500, cashback_rate_bps=200)

        response = change("cashback-rate", event_id, organizer, 600)

        assert response.status_code == 422
        assert response.json()["code"] == "QIT002032"

    def test_fee_cannot_go_below_cashback(self):
        organizer = uuid.uuid4()
        event_id = create_event(organizer, fee_rate_bps=500, cashback_rate_bps=200)

        response = change("fee-rate", event_id, organizer, 100)

        assert response.status_code == 422
        assert response.json()["code"] == "QIT002032"

    def test_reason_is_required(self):
        organizer = uuid.uuid4()
        event_id = create_event(organizer)

        response = change("fee-rate", event_id, organizer, 600, reason="   ")

        assert response.status_code == 400
        assert response.json()["code"] == "QIT000001"

    def test_only_the_event_organizer_changes(self):
        event_id = create_event(uuid.uuid4())

        response = change("fee-rate", event_id, uuid.uuid4(), 600)

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002010"


class TestCashbackHistory:
    def test_history_keeps_every_version(self):
        organizer = uuid.uuid4()
        event_id = create_event(organizer, fee_rate_bps=500, cashback_rate_bps=200)
        change("cashback-rate", event_id, organizer, 300, reason="Promoção de abertura")
        change("cashback-rate", event_id, organizer, 100, reason="Fim da promoção")

        response = events.send(
            "GET", f"/events/{event_id}/cashback-rates", headers=headers("organizer", organizer)
        )

        assert response.status_code == 200
        versions = response.json()["data"]
        assert [v["rate_bps"] for v in versions] == [100, 300, 200]
        assert [v["current"] for v in versions] == [True, False, False]
        assert versions[1]["reason"] == "Promoção de abertura"

    def test_attendee_with_credential_sees_history(self):
        event_id = create_event(uuid.uuid4())
        attendee = uuid.uuid4()
        events.send("POST", f"/events/{event_id}/attendees", headers=headers("attendee", attendee))

        response = events.send(
            "GET", f"/events/{event_id}/cashback-rates", headers=headers("attendee", attendee)
        )

        assert response.status_code == 200

    def test_outsider_does_not_see_history(self):
        event_id = create_event(uuid.uuid4())

        response = events.send("GET", f"/events/{event_id}/cashback-rates", headers=headers("attendee"))

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002010"