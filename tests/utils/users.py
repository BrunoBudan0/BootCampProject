import random
import uuid
from datetime import date, timedelta

from tests.utils.clock import today_in_sao_paulo
from tests.utils.payments import as_caller
from tests.utils.services import users

DEFAULT_PASSWORD = "uma-senha-forte-123"
MINIMUM_ATTENDEE_AGE = 18
PRIVATE_FIELDS = {"password", "password_hash", "document"}

ATTENDEE = "attendee"
ORGANIZER = "organizer"
COMPANY = "company"

REGISTRATION_ROUTE_BY_USER_TYPE = {
    ATTENDEE: "/attendees",
    ORGANIZER: "/organizers",
    COMPANY: "/companies",
}


def new_cpf() -> str:
    digits = [random.randrange(10) for _ in range(9)]
    for _ in range(2):
        remainder = sum((len(digits) + 1 - index) * digit for index, digit in enumerate(digits)) % 11
        digits.append(0 if remainder < 2 else 11 - remainder)

    text = "".join(str(digit) for digit in digits)
    return f"{text[0:3]}.{text[3:6]}.{text[6:9]}-{text[9:11]}"


def new_cnpj() -> str:
    digits = [random.randrange(10) for _ in range(8)] + [0, 0, 0, 1]
    for weights in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        remainder = sum(digit * weight for digit, weight in zip(digits, weights)) % 11
        digits.append(0 if remainder < 2 else 11 - remainder)

    text = "".join(str(digit) for digit in digits)
    return f"{text[0:2]}.{text[2:5]}.{text[5:8]}/{text[8:12]}-{text[12:14]}"


def with_wrong_check_digit(document: str) -> str:
    last_digit = int(document[-1])
    return document[:-1] + str((last_digit + 1) % 10)


def new_email() -> str:
    return f"pessoa-{uuid.uuid4().hex[:12]}@evento.com"


def birth_date_for_age(age_in_years: int) -> str:
    today = today_in_sao_paulo()
    if today.month == 2 and today.day == 29:
        return date(today.year - age_in_years, 2, 28).isoformat()

    return date(today.year - age_in_years, today.month, today.day).isoformat()


def birth_date_one_day_short_of(age_in_years: int) -> str:
    return (date.fromisoformat(birth_date_for_age(age_in_years)) + timedelta(days=1)).isoformat()


def attendee_payload(**changes) -> dict:
    payload = {
        "name": "Ana Souza",
        "email": new_email(),
        "document": new_cpf(),
        "password": DEFAULT_PASSWORD,
        "birth_date": birth_date_for_age(30),
        "phone": "(11) 98888-7777",
        "postal_code": "01310-100",
    }
    payload.update(changes)
    return payload


def organizer_payload(**changes) -> dict:
    payload = {
        "name": "Bienal Eventos",
        "email": new_email(),
        "document": new_cnpj(),
        "password": DEFAULT_PASSWORD,
        "phone": "(11) 3333-4444",
    }
    payload.update(changes)
    return payload


def company_payload(**changes) -> dict:
    payload = {
        "legal_name": "Livraria Exemplo LTDA",
        "trade_name": "Livraria Exemplo",
        "email": new_email(),
        "document": new_cnpj(),
        "password": DEFAULT_PASSWORD,
        "phone": "(11) 2222-3333",
    }
    payload.update(changes)
    return payload


PAYLOAD_BUILDER_BY_USER_TYPE = {
    ATTENDEE: attendee_payload,
    ORGANIZER: organizer_payload,
    COMPANY: company_payload,
}


def register(user_type: str, payload: dict):
    return users.send("POST", REGISTRATION_ROUTE_BY_USER_TYPE[user_type], json=payload)


def registered(user_type: str, **changes) -> dict:
    payload = PAYLOAD_BUILDER_BY_USER_TYPE[user_type](**changes)
    response = register(user_type, payload)
    assert response.status_code == 201, (
        f"A PREPARAÇÃO do teste falhou ao cadastrar {user_type}: {response.status_code} {response.text}\n"
        "O que está quebrado é o cadastro usado para montar o cenário, não a regra deste teste."
    )

    return {"id": response.json()["id"], **payload}


def login(email: str, password: str, user_type: str):
    return users.send(
        "POST",
        "/internal/login",
        json={"email": email, "password": password, "user_type": user_type},
    )


def me(user_id: str, user_type: str):
    return users.send("GET", "/me", headers=as_caller(user_id, user_type))
