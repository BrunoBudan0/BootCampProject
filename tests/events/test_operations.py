import uuid

from tests.events.helpers import Fair, create_event, headers, take_funded_credential
from tests.utils.services import events


def recharge(fair, credential_id, amount_cents=5000, key=None, organizer=None):
    return events.send(
        "POST", f"/events/{fair.event_id}/cash-recharges",
        json={
            "event_attendee_id": credential_id,
            "amount_cents": amount_cents,
            "idempotency_key": key or f"cash-{uuid.uuid4().hex}",
        },
        headers=headers("organizer", organizer or fair.organizer),
    )


def block(fair, credential_id, blocked=True, organizer=None):
    return events.send(
        "PUT", f"/event-attendees/{credential_id}/block",
        json={"blocked": blocked},
        headers=headers("organizer", organizer or fair.organizer),
    )


class TestCashRecharge:
    def test_recharge_gives_balance_to_buy(self):
        fair = Fair(price_cents=4000, balance=0)

        response = recharge(fair, fair.credential_id, 5000)

        assert response.status_code == 201
        assert fair.buy().status_code == 201

    def test_same_key_does_not_recharge_twice(self):
        fair = Fair(price_cents=4000, balance=0)
        key = f"cash-{uuid.uuid4().hex}"

        first = recharge(fair, fair.credential_id, 4000, key=key)
        second = recharge(fair, fair.credential_id, 4000, key=key)

        assert (first.status_code, second.status_code) == (201, 200)
        assert fair.buy().status_code == 201
        assert fair.buy().status_code == 409

    def test_same_key_with_another_amount_is_refused(self):
        fair = Fair(balance=0)
        key = f"cash-{uuid.uuid4().hex}"
        recharge(fair, fair.credential_id, 4000, key=key)

        response = recharge(fair, fair.credential_id, 9000, key=key)

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002025"

    def test_amount_above_the_ceiling_is_refused(self):
        fair = Fair()

        response = recharge(fair, fair.credential_id, 10_000_001)

        assert response.status_code == 400
        assert response.json()["code"] == "QIT000001"

    def test_amount_must_be_positive(self):
        fair = Fair()

        response = recharge(fair, fair.credential_id, 0)

        assert response.status_code == 422
        assert response.json()["code"] == "QIT002028"

    def test_only_organizer_recharges(self):
        fair = Fair()
        body = {"event_attendee_id": fair.credential_id, "amount_cents": 100, "idempotency_key": "cash-12345678"}

        response = events.send(
            "POST", f"/events/{fair.event_id}/cash-recharges", json=body,
            headers=headers("attendee", fair.attendee),
        )

        assert response.status_code == 403
        assert response.json()["code"] == "QIT002004"

    def test_credential_of_another_event(self):
        fair = Fair()
        other_organizer = uuid.uuid4()
        other_event = create_event(other_organizer)
        _, foreign_credential = take_funded_credential(other_event, other_organizer, 0)

        response = recharge(fair, foreign_credential)

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002014"


class TestBlock:
    def test_blocked_credential_cannot_buy_until_released(self):
        fair = Fair()

        blocked = block(fair, fair.credential_id, True)
        refused = fair.buy()
        released = block(fair, fair.credential_id, False)

        assert blocked.status_code == 200
        assert blocked.json()["blocked"] is True
        assert refused.status_code == 409
        assert refused.json()["code"] == "QIT002015"
        assert released.json()["blocked"] is False
        assert fair.buy().status_code == 201

    def test_blocking_twice_is_fine(self):
        fair = Fair()

        block(fair, fair.credential_id, True)
        response = block(fair, fair.credential_id, True)

        assert response.status_code == 200
        assert response.json()["blocked"] is True

    def test_blocked_credential_gets_no_recharge(self):
        fair = Fair()
        block(fair, fair.credential_id, True)

        response = recharge(fair, fair.credential_id)

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002015"

    def test_other_organizer_gets_404(self):
        fair = Fair()

        response = block(fair, fair.credential_id, True, organizer=uuid.uuid4())

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002014"


class TestFeeCharges:
    def test_each_charge_shows_the_rate_used(self):
        fair = Fair(price_cents=4000, fee_rate_bps=500)
        fair.buy()
        fair.as_organizer("PUT", f"/events/{fair.event_id}/fee-rate", json={"rate_bps": 700, "reason": "Alta"})
        fair.buy()

        audit = fair.as_organizer("GET", f"/events/{fair.event_id}/fee-charges").json()

        assert sorted(c["rate_bps"] for c in audit["data"]) == [500, 700]
        assert audit["net_cents"] == 200 + 280

    def test_other_organizer_gets_404(self):
        fair = Fair()

        response = events.send(
            "GET", f"/events/{fair.event_id}/fee-charges", headers=headers("organizer")
        )

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002010"


class TestReconciliation:
    def test_sum_is_zero_after_sales_and_refund(self):
        fair = Fair(price_cents=4000)
        fair.buy()
        refunded = fair.buy().json()["id"]
        fair.refund(refunded)

        report = fair.as_organizer("GET", f"/events/{fair.event_id}/reconciliation").json()

        assert report["ok"] is True
        assert report["sum_cents"] == 0
        assert len(report["accounts"]) == 4
        assert report["purchases"]["paid"]["count"] == 1
        assert report["purchases"]["refunded"]["count"] == 1
        assert report["fee_net_cents"] == 200

    def test_only_the_organizer_reconciles(self):
        fair = Fair()

        response = events.send(
            "GET", f"/events/{fair.event_id}/reconciliation", headers=headers("organizer")
        )

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002010"
