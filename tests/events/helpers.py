import random
import uuid

from tests.utils.services import events, users


def headers(user_type, user_id=None):
    return {"X-User-Id": str(user_id or uuid.uuid4()), "X-User-Type": user_type}


def random_cnpj():
    base = [random.randint(0, 9) for _ in range(12)]
    for weights in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        rest = sum(d * w for d, w in zip(base, weights)) % 11
        base.append(0 if rest < 2 else 11 - rest)
    return "".join(map(str, base))


def create_company():
    suffix = uuid.uuid4().hex[:8]
    response = users.send("POST", "/companies", json={
        "legal_name": f"Livraria {suffix} LTDA",
        "trade_name": f"Livraria {suffix}",
        "email": f"livraria-{suffix}@teste.com",
        "document": random_cnpj(),
        "password": "senha-forte-123",
        "phone": "11999990000",
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_event(organizer_id, fee_rate_bps=500, cashback_rate_bps=200):
    response = events.send("POST", "/events", json={
        "name": "Bienal do Livro",
        "location": "São Paulo",
        "fee_rate_bps": fee_rate_bps,
        "cashback_rate_bps": cashback_rate_bps,
    }, headers=headers("organizer", organizer_id))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_stand(organizer_id, event_id, company_id, stand_name="Livraria A"):
    response = events.send(
        "POST", f"/events/{event_id}/companies",
        json={"company_id": company_id, "stand_name": stand_name},
        headers=headers("organizer", organizer_id),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_product(company_id, stand_id, price_cents=4000, stock=10, barcode=None):
    response = events.send("POST", "/products", json={
        "event_company_id": stand_id,
        "name": "Dom Casmurro",
        "barcode": barcode or uuid.uuid4().hex[:13],
        "price_cents": price_cents,
        "stock": stock,
    }, headers=headers("company", company_id))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def take_credential(event_id, attendee_id=None):
    attendee_id = attendee_id or uuid.uuid4()
    response = events.send("POST", f"/events/{event_id}/attendees", headers=headers("attendee", attendee_id))
    assert response.status_code == 201, response.text
    return attendee_id, response.json()["id"]


def get_product(product_id):
    return events.send("GET", f"/products/{product_id}", headers=headers("attendee")).json()


def take_funded_credential(event_id, organizer_id, amount_cents=100_000):
    # credencial com saldo, carregada pela recarga em espécie da própria API
    attendee_id = uuid.uuid4()
    response = events.send("POST", f"/events/{event_id}/attendees", headers=headers("attendee", attendee_id))
    assert response.status_code == 201, response.text
    credential_id = response.json()["id"]

    if amount_cents:
        recharge = events.send("POST", f"/events/{event_id}/cash-recharges", json={
            "event_attendee_id": credential_id,
            "amount_cents": amount_cents,
            "idempotency_key": f"cash-{uuid.uuid4().hex}",
        }, headers=headers("organizer", organizer_id))
        assert recharge.status_code == 201, recharge.text

    return attendee_id, credential_id


class Fair:
    """Um evento montado: stand com produto e uma pessoa credenciada."""

    def __init__(self, price_cents=4000, stock=10, fee_rate_bps=500, cashback_rate_bps=200, balance=100_000):
        self.organizer = uuid.uuid4()
        self.event_id = create_event(self.organizer, fee_rate_bps, cashback_rate_bps)
        self.company_id = create_company()
        self.stand_id = create_stand(self.organizer, self.event_id, self.company_id)
        self.product_id = create_product(self.company_id, self.stand_id, price_cents, stock)
        self.attendee, self.credential_id = take_funded_credential(self.event_id, self.organizer, balance)

    def buyer(self, balance=100_000):
        return take_funded_credential(self.event_id, self.organizer, balance)

    def buy(self, items=None, attendee=None, credential_id=None, key=None):
        body = {
            "event_attendee_id": credential_id or self.credential_id,
            "event_company_id": self.stand_id,
            "items": items or [{"product_id": self.product_id, "quantity": 1}],
            "idempotency_key": key or f"app-{uuid.uuid4().hex}",
        }
        return events.send("POST", "/purchases", json=body, headers=headers("attendee", attendee or self.attendee))

    def receipt(self, purchase_id, user_type="attendee", user_id=None):
        return events.send(
            "GET", f"/purchases/{purchase_id}", headers=headers(user_type, user_id or self.attendee)
        )

    def refund(self, purchase_id, user_type="attendee", user_id=None, reason="Produto com defeito"):
        return events.send(
            "POST", f"/purchases/{purchase_id}/refund",
            json={"reason": reason},
            headers=headers(user_type, user_id or self.attendee),
        )

    def as_organizer(self, method, path, **kwargs):
        return events.send(method, path, headers=headers("organizer", self.organizer), **kwargs)
