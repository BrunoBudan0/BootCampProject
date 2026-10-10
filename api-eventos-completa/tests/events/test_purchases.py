import uuid
from concurrent.futures import ThreadPoolExecutor

from tests.events.helpers import Fair, create_company, create_product, create_stand, get_product, headers
from tests.utils.services import events


class TestReserve:
    def test_purchase_is_paid_with_prices_from_the_database(self):
        fair = Fair(price_cents=4000, stock=10)

        response = fair.buy([{"product_id": fair.product_id, "quantity": 2}])

        assert response.status_code == 201
        receipt = response.json()
        assert receipt["status"] == "paid"
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
        buyers = [fair.buyer() for _ in range(20)]

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
        buyers = [fair.buyer() for _ in range(10)]

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


class TestIdempotency:
    def test_resend_returns_the_same_purchase(self):
        fair = Fair(stock=10)
        key = f"app-{uuid.uuid4().hex}"

        first = fair.buy(key=key)
        second = fair.buy(key=key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert get_product(fair.product_id)["stock"] == 9

    def test_same_cart_in_another_order_is_still_a_resend(self):
        fair = Fair(stock=10)
        other = create_product(fair.company_id, fair.stand_id, stock=10)
        key = f"app-{uuid.uuid4().hex}"

        fair.buy([{"product_id": fair.product_id, "quantity": 2}, {"product_id": other, "quantity": 1}], key=key)
        response = fair.buy([
            {"product_id": other, "quantity": 1},
            {"product_id": fair.product_id, "quantity": 1},
            {"product_id": fair.product_id, "quantity": 1},
        ], key=key)

        assert response.status_code == 200
        assert get_product(fair.product_id)["stock"] == 8

    def test_same_key_with_another_cart_is_refused(self):
        fair = Fair(stock=10)
        key = f"app-{uuid.uuid4().hex}"
        fair.buy(key=key)

        response = fair.buy([{"product_id": fair.product_id, "quantity": 5}], key=key)

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002025"
        assert get_product(fair.product_id)["stock"] == 9

    def test_key_of_someone_else_never_shows_their_receipt(self):
        fair = Fair(stock=10)
        key = f"app-{uuid.uuid4().hex}"
        fair.buy(key=key)
        stranger, stranger_credential = fair.buyer()

        response = fair.buy(key=key, attendee=stranger, credential_id=stranger_credential)

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002025"

    def test_double_click_at_the_same_time_buys_once(self):
        fair = Fair(stock=10)
        key = f"app-{uuid.uuid4().hex}"

        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(lambda _: fair.buy(key=key), range(10)))

        statuses = sorted(r.status_code for r in responses)
        assert statuses == [200] * 9 + [201]
        assert len({r.json()["id"] for r in responses}) == 1
        assert get_product(fair.product_id)["stock"] == 9


class TestPayment:
    def test_without_balance_the_purchase_is_canceled_and_stock_comes_back(self):
        fair = Fair(price_cents=4000, stock=10, balance=3000)
        key = f"app-{uuid.uuid4().hex}"

        response = fair.buy(key=key)

        assert response.status_code == 409
        assert response.json()["code"] == "QIT002021"
        assert get_product(fair.product_id)["stock"] == 10

        resend = fair.buy(key=key)
        assert resend.status_code == 200
        assert resend.json()["status"] == "canceled"

    def test_balance_pays_exactly_what_it_has(self):
        # 4000 de compra e 80 de cashback: a pessoa precisa ter 4000 na hora
        fair = Fair(price_cents=4000, stock=10, balance=4000)

        response = fair.buy()

        assert response.status_code == 201
        assert response.json()["status"] == "paid"

    def test_event_without_fee_still_sells(self):
        fair = Fair(fee_rate_bps=0, cashback_rate_bps=0)

        response = fair.buy()

        assert response.status_code == 201
        assert response.json()["status"] == "paid"
        assert response.json()["fee_cents"] == 0

    def test_resend_of_a_paid_purchase_does_not_charge_again(self):
        fair = Fair(price_cents=4000, balance=5000)
        key = f"app-{uuid.uuid4().hex}"

        first = fair.buy(key=key)
        second = fair.buy(key=key)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["status"] == "paid"
        # se tivesse cobrado de novo, 5000 - 3920 = 1080 não pagaria outra de 4000
        assert fair.buy().status_code == 409
