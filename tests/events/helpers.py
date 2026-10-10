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