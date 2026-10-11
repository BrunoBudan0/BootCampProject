import uuid

from tests.gateway.helpers import User


def test_a_whole_fair_through_the_gateway():
    organizer = User("organizer")
    company = User("company")
    attendee = User("attendee")

    event = organizer.send("POST", "/events", json={
        "name": "Bienal do Livro", "location": "São Paulo", "fee_rate_bps": 500, "cashback_rate_bps": 200,
    })
    assert event.status_code == 201, event.text
    event_id = event.json()["id"]

    stand = organizer.send("POST", f"/events/{event_id}/companies", json={
        "company_id": company.id, "stand_name": "Livraria Teste",
    })
    assert stand.status_code == 201, stand.text
    stand_id = stand.json()["id"]

    product = company.send("POST", "/products", json={
        "event_company_id": stand_id, "name": "Dom Casmurro", "barcode": "9788535910663", "price_cents": 4000, "stock": 3,
    })
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]

    credential = attendee.send("POST", f"/events/{event_id}/attendees")
    assert credential.status_code == 201, credential.text
    credential_id = credential.json()["id"]

    recharge = organizer.send("POST", f"/events/{event_id}/cash-recharges", json={
        "event_attendee_id": credential_id, "amount_cents": 5000, "idempotency_key": f"cash-{uuid.uuid4().hex}",
    })
    assert recharge.status_code == 201, recharge.text

    scan = attendee.send("GET", "/products", params={"event_company_id": stand_id, "barcode": "9788535910663"})
    assert [p["id"] for p in scan.json()["data"]] == [product_id]

    purchase = attendee.send("POST", "/purchases", json={
        "event_attendee_id": credential_id, "event_company_id": stand_id,
        "items": [{"product_id": product_id, "quantity": 1}], "idempotency_key": f"app-{uuid.uuid4().hex}",
    })
    assert purchase.status_code == 201, purchase.text
    assert purchase.json()["status"] == "paid"

    accounts = attendee.send("GET", "/accounts")
    assert accounts.status_code == 200, accounts.text
    # R$ 50 de recarga, R$ 40 de compra e R$ 0,80 de cashback
    assert [a["balance_cents"] for a in accounts.json()["data"]] == [1080]

    refund = attendee.send("POST", f"/purchases/{purchase.json()['id']}/refund", json={"reason": "Desisti"})
    assert refund.status_code == 201, refund.text
    assert attendee.send("GET", "/accounts").json()["data"][0]["balance_cents"] == 5000

    closing = organizer.send("GET", f"/events/{event_id}/reconciliation")
    assert closing.status_code == 200, closing.text
    assert closing.json()["ok"] is True
    assert closing.json()["sum_cents"] == 0
