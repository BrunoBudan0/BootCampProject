import pytest

from tests.utils.payments import assert_error, is_uuid
from tests.utils.services import payments, users
from tests.utils.users import (
    ATTENDEE,
    COMPANY,
    MINIMUM_ATTENDEE_AGE,
    ORGANIZER,
    PAYLOAD_BUILDER_BY_USER_TYPE,
    PRIVATE_FIELDS,
    attendee_payload,
    birth_date_for_age,
    birth_date_one_day_short_of,
    company_payload,
    me,
    new_cnpj,
    new_cpf,
    new_email,
    organizer_payload,
    register,
    registered,
    with_wrong_check_digit,
)

ALL_USER_TYPES = [ATTENDEE, ORGANIZER, COMPANY]


@pytest.mark.parametrize("user_type", ALL_USER_TYPES)
class TestRegistrationOfEveryUserType:
    def test_registers_and_returns_uuid_without_password_or_document(self, user_type):
        response = register(user_type, PAYLOAD_BUILDER_BY_USER_TYPE[user_type]())

        assert response.status_code == 201
        assert is_uuid(response.json()["id"])
        assert response.json()["user_type"] == user_type
        assert PRIVATE_FIELDS.isdisjoint(response.json())

    def test_email_is_kept_in_lowercase(self, user_type):
        payload = PAYLOAD_BUILDER_BY_USER_TYPE[user_type](email=new_email().upper())

        response = register(user_type, payload)

        assert response.status_code == 201
        assert response.json()["email"] == payload["email"].lower()
        assert me(response.json()["id"], user_type).json()["email"] == payload["email"].lower()

    def test_same_document_twice_in_the_same_type_is_refused(self, user_type):
        first = registered(user_type)

        second = PAYLOAD_BUILDER_BY_USER_TYPE[user_type](document=first["document"])

        assert_error(register(user_type, second), 409, "QIT002006")

    def test_same_email_twice_in_the_same_type_is_refused(self, user_type):
        first = registered(user_type)

        second = PAYLOAD_BUILDER_BY_USER_TYPE[user_type](email=first["email"])

        assert_error(register(user_type, second), 409, "QIT002007")

    def test_email_is_compared_ignoring_case(self, user_type):
        first = registered(user_type)

        second = PAYLOAD_BUILDER_BY_USER_TYPE[user_type](email=first["email"].upper())

        assert_error(register(user_type, second), 409, "QIT002007")

    def test_missing_password_is_refused(self, user_type):
        payload = PAYLOAD_BUILDER_BY_USER_TYPE[user_type]()
        del payload["password"]

        assert_error(register(user_type, payload), 400, "QIT000001")

    def test_short_password_is_refused(self, user_type):
        payload = PAYLOAD_BUILDER_BY_USER_TYPE[user_type](password="1234567")

        assert_error(register(user_type, payload), 400, "QIT000001")

    def test_email_outside_ascii_is_refused(self, user_type):
        """Cada "İ" vira dois caracteres em minúscula: 211 viram 411, e a
        coluna tem 255."""
        payload = PAYLOAD_BUILDER_BY_USER_TYPE[user_type](email="İ" * 200 + "@evento.com")

        assert_error(register(user_type, payload), 400, "QIT000001")

    def test_malformed_email_is_refused(self, user_type):
        payload = PAYLOAD_BUILDER_BY_USER_TYPE[user_type](email="isto-nao-e-um-email")

        assert_error(register(user_type, payload), 400, "QIT000001")

    def test_unknown_field_is_refused(self, user_type):
        payload = PAYLOAD_BUILDER_BY_USER_TYPE[user_type](is_admin=True)

        assert_error(register(user_type, payload), 400, "QIT000001")


class TestSamePersonInMoreThanOneRole:
    def test_attendee_and_organizer_can_share_cpf_and_email(self):
        shared = {"document": new_cpf(), "email": new_email()}

        as_attendee = register(ATTENDEE, attendee_payload(**shared))
        as_organizer = register(ORGANIZER, organizer_payload(**shared))

        assert as_attendee.status_code == 201
        assert as_organizer.status_code == 201
        assert as_attendee.json()["id"] != as_organizer.json()["id"]

    def test_organizer_and_company_can_share_cnpj_and_email(self):
        shared = {"document": new_cnpj(), "email": new_email()}

        as_organizer = register(ORGANIZER, organizer_payload(**shared))
        as_company = register(COMPANY, company_payload(**shared))

        assert as_organizer.status_code == 201
        assert as_company.status_code == 201
        assert as_organizer.json()["id"] != as_company.json()["id"]


class TestAttendeeRules:
    def test_cpf_with_wrong_check_digit_is_refused(self):
        payload = attendee_payload(document=with_wrong_check_digit(new_cpf()))

        assert_error(register(ATTENDEE, payload), 422, "QIT002005")

    def test_cpf_with_all_digits_equal_is_refused(self):
        payload = attendee_payload(document="111.111.111-11")

        assert_error(register(ATTENDEE, payload), 422, "QIT002005")

    def test_cpf_without_mask_is_refused_by_the_schema(self):
        payload = attendee_payload(document=new_cpf().replace(".", "").replace("-", ""))

        assert_error(register(ATTENDEE, payload), 400, "QIT000001")

    def test_cnpj_is_not_an_attendee_document(self):
        payload = attendee_payload(document=new_cnpj())

        assert_error(register(ATTENDEE, payload), 400, "QIT000001")

    def test_missing_birth_date_is_refused(self):
        payload = attendee_payload()
        del payload["birth_date"]

        assert_error(register(ATTENDEE, payload), 400, "QIT000001")

    def test_birth_date_that_does_not_exist_is_refused(self):
        payload = attendee_payload(birth_date="2000-02-30")

        assert_error(register(ATTENDEE, payload), 422, "QIT002008")

    def test_exactly_the_minimum_age_is_accepted(self):
        payload = attendee_payload(birth_date=birth_date_for_age(MINIMUM_ATTENDEE_AGE))

        assert register(ATTENDEE, payload).status_code == 201

    def test_one_day_short_of_the_minimum_age_is_refused(self):
        payload = attendee_payload(birth_date=birth_date_one_day_short_of(MINIMUM_ATTENDEE_AGE))

        assert_error(register(ATTENDEE, payload), 422, "QIT002008")

    def test_birth_date_in_the_future_is_refused(self):
        payload = attendee_payload(birth_date=birth_date_for_age(-1))

        assert_error(register(ATTENDEE, payload), 422, "QIT002008")


class TestOrganizerRules:
    def test_accepts_cpf(self):
        assert register(ORGANIZER, organizer_payload(document=new_cpf())).status_code == 201

    def test_accepts_cnpj(self):
        assert register(ORGANIZER, organizer_payload(document=new_cnpj())).status_code == 201

    def test_cnpj_with_wrong_check_digit_is_refused(self):
        payload = organizer_payload(document=with_wrong_check_digit(new_cnpj()))

        assert_error(register(ORGANIZER, payload), 422, "QIT002005")

    def test_cpf_with_wrong_check_digit_is_refused(self):
        payload = organizer_payload(document=with_wrong_check_digit(new_cpf()))

        assert_error(register(ORGANIZER, payload), 422, "QIT002005")

    def test_cpf_with_all_digits_equal_is_refused(self):
        """111.111.111-11 acerta os dígitos verificadores: só a regra própria o recusa."""
        payload = organizer_payload(document="111.111.111-11")

        assert_error(register(ORGANIZER, payload), 422, "QIT002005")


class TestCompanyRules:
    def test_cnpj_with_wrong_check_digit_is_refused(self):
        payload = company_payload(document=with_wrong_check_digit(new_cnpj()))

        assert_error(register(COMPANY, payload), 422, "QIT002005")

    def test_cnpj_with_all_digits_equal_is_refused(self):
        """00.000.000/0000-00 acerta os dígitos verificadores: só a regra própria o recusa."""
        payload = company_payload(document="00.000.000/0000-00")

        assert_error(register(COMPANY, payload), 422, "QIT002005")

    def test_cpf_is_not_a_company_document(self):
        payload = company_payload(document=new_cpf())

        assert_error(register(COMPANY, payload), 400, "QIT000001")

    def test_missing_trade_name_is_refused(self):
        payload = company_payload()
        del payload["trade_name"]

        assert_error(register(COMPANY, payload), 400, "QIT000001")


class TestRegistrationDoor:
    def test_without_token_is_refused(self):
        response = users.send("POST", "/attendees", json=attendee_payload(), token=None)

        assert_error(response, 403, "QIT000002")

    def test_token_of_another_api_is_refused(self):
        response = users.send("POST", "/attendees", json=attendee_payload(), token=payments.token)

        assert_error(response, 403, "QIT000002")
