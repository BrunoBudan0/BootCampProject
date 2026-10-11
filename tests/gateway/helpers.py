import random
import uuid

from tests.utils.services import gateway

PASSWORD = "senha-forte-123"


def _digits(base, weights_list):
    for weights in weights_list:
        rest = sum(d * w for d, w in zip(base, weights)) % 11
        base.append(0 if rest < 2 else 11 - rest)
    return "".join(map(str, base))


def random_cpf():
    base = [random.randint(0, 9) for _ in range(9)]
    d = _digits(base, [range(10, 1, -1), range(11, 1, -1)])
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def random_cnpj():
    base = [random.randint(0, 9) for _ in range(12)]
    d = _digits(base, [[5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]])
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def new_email(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}@teste.com"


def signup(user_type):
    email = new_email(user_type)
    if user_type == "attendee":
        body = {"name": "Ana Souza", "email": email, "document": random_cpf(),
                "password": PASSWORD, "birth_date": "1995-05-20"}
        path = "/attendees"
    elif user_type == "organizer":
        body = {"name": "Org Feiras", "email": email, "document": random_cpf(), "password": PASSWORD}
        path = "/organizers"
    else:
        body = {"legal_name": "Livraria Teste LTDA", "trade_name": "Livraria Teste", "email": email,
                "document": random_cnpj(), "password": PASSWORD}
        path = "/companies"
    response = gateway.send("POST", path, json=body)
    assert response.status_code == 201, response.text
    return email, response.json()["id"]


def login(email, user_type, password=PASSWORD):
    return gateway.send("POST", "/auth/login", json={"email": email, "password": password, "user_type": user_type})


class User:
    """Alguém cadastrado e logado pelo Gateway."""

    def __init__(self, user_type):
        self.user_type = user_type
        self.email, self.id = signup(user_type)
        response = login(self.email, user_type)
        assert response.status_code == 200, response.text
        self.token = response.json()["token"]

    def send(self, method, path, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {}, **{"AUTH-TOKEN": self.token})
        return gateway.send(method, path, headers=headers, **kwargs)
