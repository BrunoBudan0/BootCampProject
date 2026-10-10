import uuid

from tests.events.helpers import Fair, get_product


class TestReceipt:
    def test_buyer_stand_and_organizer_see_the_receipt(self):
        fair = Fair()
        purchase_id = fair.buy().json()["id"]

        assert fair.receipt(purchase_id).status_code == 200
        assert fair.receipt(purchase_id, "company", fair.company_id).status_code == 200
        assert fair.receipt(purchase_id, "organizer", fair.organizer).status_code == 200

    def test_receipt_brings_items_and_amounts(self):
        fair = Fair(price_cents=4000)
        purchase_id = fair.buy([{"product_id": fair.product_id, "quantity": 2}]).json()["id"]

        receipt = fair.receipt(purchase_id).json()

        assert receipt["status"] == "paid"
        assert receipt["items"][0]["subtotal_cents"] == 8000
        assert receipt["paid_cents"] == 8000 - 160
        assert receipt["refund"] is None

    def test_stranger_gets_404(self):
        fair = Fair()
        purchase_id = fair.buy().json()["id"]

        response = fair.receipt(purchase_id, "attendee", uuid.uuid4())

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002023"


class TestRefund:
    def test_buyer_refunds_and_stock_comes_back(self):
        fair = Fair(stock=10)
        purchase_id = fair.buy([{"product_id": fair.product_id, "quantity": 3}]).json()["id"]

        response = fair.refund(purchase_id, reason="Desisti da compra")

        assert response.status_code == 201
        receipt = response.json()
        assert receipt["status"] == "refunded"
        assert receipt["refund"]["reason"] == "Desisti da compra"
        assert get_product(fair.product_id)["stock"] == 10

    def test_stand_and_organizer_can_refund(self):
        fair = Fair()
        first = fair.buy().json()["id"]
        second = fair.buy().json()["id"]

        assert fair.refund(first, "company", fair.company_id).status_code == 201
        assert fair.refund(second, "organizer", fair.organizer).status_code == 201

    def test_refund_happens_once(self):
        fair = Fair()
        purchase_id = fair.buy().json()["id"]
        fair.refund(purchase_id)

        response = fair.refund(purchase_id)

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002026"

    def test_canceled_purchase_is_not_refundable(self):
        fair = Fair(price_cents=4000, balance=100)
        key = f"app-{uuid.uuid4().hex}"
        fair.buy(key=key)
        purchase_id = fair.buy(key=key).json()["id"]

        response = fair.refund(purchase_id)

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002026"

    def test_fee_is_given_back_in_the_audit(self):
        fair = Fair(price_cents=4000, fee_rate_bps=500)
        purchase_id = fair.buy().json()["id"]
        fair.refund(purchase_id)

        audit = fair.as_organizer("GET", f"/events/{fair.event_id}/fee-charges").json()

        kinds = sorted((charge["kind"], charge["amount_cents"]) for charge in audit["data"])
        assert kinds == [("charge", 200), ("refund", -200)]
        assert audit["net_cents"] == 0

    def test_reason_is_required(self):
        fair = Fair()
        purchase_id = fair.buy().json()["id"]

        response = fair.refund(purchase_id, reason=" ")

        assert response.status_code == 400
        assert response.json()["code"] == "QIT000001"

    def test_stranger_cannot_refund(self):
        fair = Fair()
        purchase_id = fair.buy().json()["id"]

        response = fair.refund(purchase_id, "attendee", uuid.uuid4())

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002023"
