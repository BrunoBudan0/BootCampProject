import uuid
from concurrent.futures import ThreadPoolExecutor

from tests.events.helpers import (
    create_company,
    create_event,
    create_product,
    create_stand,
    get_product,
    headers,
    take_credential,
)
from tests.utils.services import events


class Fair:
    """Um evento montado: stand com produto e uma pessoa credenciada."""

    def __init__(self, price_cents=4000, stock=10, fee_rate_bps=500, cashback_rate_bps=200):
        self.organizer = uuid.uuid4()
        self.event_id = create_event(self.organizer, fee_rate_bps, cashback_rate_bps)
        self.company_id = create_company()
        self.stand_id = create_stand(self.organizer, self.event_id, self.company_id)
        self.product_id = create_product(self.company_id, self.stand_id, price_cents, stock)
        self.attendee, self.credential_id = take_credential(self.event_id)

    def buy(self, items=None, attendee=None, credential_id=None, key=None):
        body = {
            "event_attendee_id": credential_id or self.credential_id,
            "event_company_id": self.stand_id,
            "items": items or [{"product_id": self.product_id, "quantity": 1}],
            "idempotency_key": key or f"app-{uuid.uuid4().hex}",
        }
        return events.send("POST", "/purchases", json=body, headers=headers("attendee", attendee or self.attendee))


class TestReserve:
    def test_purchase_is_reserved_with_prices_from_the_database(self):
        fair = Fair(price_cents=4000, stock=10)

        response = fair.buy([{"product_id": fair.product_id, "quantity": 2}])

        assert response.status_code == 201
        receipt = response.json()
        assert receipt["status"] == "pending"
        assert receipt["total_cents"] == 8000
        assert receipt["fee_cents"] == 400
        assert receipt["cashback_cents"] == 160
        assert receipt["items"][0]["unit_price_cents"] == 4000
        assert get_product(fair.product_id)["stock"] == 8

    def test_same_product_in_two_lines_is_summed(self):
        fair = Fair(stock=10)

        response = fair.buy([
            {"product_id": fair.product_id, "quantity": 1},
            {"product_id": fair.product_id, "quantity": 2},
        ])

        assert response.status_code == 201
        assert response.json()["items"][0]["quantity"] == 3
        assert get_product(fair.product_id)["stock"] == 7

    def test_app_cannot_send_the_price(self):
        fair = Fair()

        response = fair.buy([{"product_id": fair.product_id, "quantity": 1, "price_cents": 1}])

        assert response.status_code == 400
        assert response.json()["code"] == "QIT000001"


class TestRefusals:
    def test_not_enough_stock_changes_nothing(self):
        fair = Fair(stock=2)
        other = create_product(fair.company_id, fair.stand_id, stock=5)

        response = fair.buy([
            {"product_id": other, "quantity": 1},
            {"product_id": fair.product_id, "quantity": 3},
        ])

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002019"
        assert get_product(fair.product_id)["stock"] == 2
        assert get_product(other)["stock"] == 5

    def test_inactive_product(self):
        fair = Fair()
        events.send(
            "PUT", f"/products/{fair.product_id}", json={"active": False},
            headers=headers("company", fair.company_id),
        )

        response = fair.buy()

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002017"

    def test_product_of_another_stand(self):
        fair = Fair()
        other_company = create_company()
        other_stand = create_stand(fair.organizer, fair.event_id, other_company, "Livraria B")
        other_product = create_product(other_company, other_stand)

        response = fair.buy([{"product_id": other_product, "quantity": 1}])

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002016"

    def test_someone_else_credential(self):
        fair = Fair()

        response = fair.buy(attendee=uuid.uuid4())

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002014"

    def test_only_attendee_buys(self):
        fair = Fair()
        body = {
            "event_attendee_id": fair.credential_id,
            "event_company_id": fair.stand_id,
            "items": [{"product_id": fair.product_id, "quantity": 1}],
            "idempotency_key": f"app-{uuid.uuid4().hex}",
        }

        response = events.send("POST", "/purchases", json=body, headers=headers("company", fair.company_id))

        assert response.status_code == 403
        assert response.json()["code"] == "QIT002004"


class TestConcurrency:
    def test_last_units_are_never_sold_twice(self):
        fair = Fair(stock=5)
        buyers = [take_credential(fair.event_id) for _ in range(20)]

        def buy(buyer):
            attendee, credential_id = buyer
            return fair.buy(attendee=attendee, credential_id=credential_id).status_code

        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(buy, buyers))

        assert results.count(201) == 5
        assert results.count(409) == 15
        assert get_product(fair.product_id)["stock"] == 0

    def test_crossed_carts_do_not_deadlock(self):
        fair = Fair(stock=1000)
        other = create_product(fair.company_id, fair.stand_id, stock=1000)
        buyers = [take_credential(fair.event_id) for _ in range(10)]

        def buy(index):
            attendee, credential_id = buyers[index]
            first, second = (fair.product_id, other) if index % 2 else (other, fair.product_id)
            items = [{"product_id": first, "quantity": 1}, {"product_id": second, "quantity": 1}]
            return fair.buy(items, attendee=attendee, credential_id=credential_id).status_code

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(buy, range(10)))

        assert results == [201] * 10
        assert get_product(fair.product_id)["stock"] == 990
        assert get_product(other)["stock"] == 990