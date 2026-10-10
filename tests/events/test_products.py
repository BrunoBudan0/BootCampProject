import uuid

from tests.utils.services import events


def headers(user_type, user_id=None):
    return {"X-User-Id": user_id or str(uuid.uuid4()), "X-User-Type": user_type}


def new_product_body(**changes):
    body = {
        "event_company_id": str(uuid.uuid4()),
        "name": "Dom Casmurro",
        "barcode": "9788535910663",
        "price_cents": 4000,
        "stock": 10,
    }
    body.update(changes)
    return body


# o caminho feliz entra junto com a rota de stand (POST /events/{id}/companies)

class TestCreateProduct:
    def test_only_company_creates(self):
        response = events.send("POST", "/products", json=new_product_body(), headers=headers("attendee"))

        assert response.status_code == 403
        assert response.json()["code"] == "QIT002004"

    def test_unknown_stand(self):
        response = events.send("POST", "/products", json=new_product_body(), headers=headers("company"))

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002010"

    def test_price_must_be_positive(self):
        response = events.send(
            "POST", "/products", json=new_product_body(price_cents=0), headers=headers("company")
        )

        assert response.status_code == 400
        assert response.json()["code"] == "QIT000001"


class TestSearchProducts:
    def test_needs_event_or_stand(self):
        response = events.send("GET", "/products?barcode=9788535910663", headers=headers("attendee"))

        assert response.status_code == 400
        assert response.json()["code"] == "QIT000001"

    def test_scan_unknown_barcode_is_empty(self):
        path = f"/products?event_id={uuid.uuid4()}&barcode=0000000000000"
        response = events.send("GET", path, headers=headers("attendee"))

        assert response.status_code == 200
        assert response.json()["data"] == []


class TestGetAndUpdateProduct:
    def test_unknown_product_is_404(self):
        response = events.send("GET", f"/products/{uuid.uuid4()}", headers=headers("attendee"))

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002016"

    def test_update_unknown_product_is_404(self):
        response = events.send(
            "PUT", f"/products/{uuid.uuid4()}", json={"price_cents": 100}, headers=headers("company")
        )

        assert response.status_code == 404
        assert response.json()["code"] == "QIT002016"

        

class TestProductOnRealStand:
    # precisa de Usuários e Pagamentos de pé
    def test_company_creates_and_attendee_scans(self):
        from tests.events.helpers import create_company, create_event, create_stand

        organizer = uuid.uuid4()
        event_id = create_event(organizer)
        company_id = create_company()
        stand_id = create_stand(organizer, event_id, company_id)

        created = events.send(
            "POST", "/products",
            json=new_product_body(event_company_id=stand_id),
            headers=headers("company", company_id),
        )
        assert created.status_code == 201

        duplicated = events.send(
            "POST", "/products",
            json=new_product_body(event_company_id=stand_id),
            headers=headers("company", company_id),
        )
        assert duplicated.status_code == 409
        assert duplicated.json()["code"] == "QIT002018"

        scanned = events.send(
            "GET", f"/products?event_company_id={stand_id}&barcode=9788535910663",
            headers=headers("attendee"),
        )
        assert scanned.status_code == 200
        assert [p["id"] for p in scanned.json()["data"]] == [created.json()["id"]]