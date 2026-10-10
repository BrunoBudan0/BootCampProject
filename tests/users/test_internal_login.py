import pytest

from tests.utils.payments import assert_error, same_refusal
from tests.utils.services import payments, users
from tests.utils.users import (
    ATTENDEE,
    COMPANY,
    DEFAULT_PASSWORD,
    ORGANIZER,
    login,
    new_email,
    registered,
)

PASSWORD_FIELDS = {"password", "password_hash"}


@pytest.mark.parametrize("user_type", [ATTENDEE, ORGANIZER, COMPANY])
class TestLoginOfEveryUserType:
    def test_right_password_returns_the_user(self, user_type):
        user = registered(user_type)

        response = login(user["email"], DEFAULT_PASSWORD, user_type)

        assert response.status_code == 200
        assert response.json()["id"] == user["id"]
        assert response.json()["user_type"] == user_type
        assert PASSWORD_FIELDS.isdisjoint(response.json())

    def test_wrong_password_is_refused(self, user_type):
        user = registered(user_type)

        assert_error(login(user["email"], "senha-errada-123", user_type), 401, "QIT002001")


class TestLoginRules:
    def test_unknown_email_is_refused(self):
        assert_error(login(new_email(), DEFAULT_PASSWORD, ATTENDEE), 401, "QIT002001")

    def test_wrong_password_and_unknown_email_look_the_same(self):
        user = registered(ATTENDEE)

        wrong_password = login(user["email"], "senha-errada-123", ATTENDEE)
        unknown_email = login(new_email(), DEFAULT_PASSWORD, ATTENDEE)

        assert same_refusal(wrong_password, unknown_email)

    def test_email_is_compared_ignoring_case(self):
        user = registered(ATTENDEE)

        response = login(user["email"].upper(), DEFAULT_PASSWORD, ATTENDEE)

        assert response.status_code == 200
        assert response.json()["id"] == user["id"]

    def test_login_only_looks_at_the_table_of_the_informed_type(self):
        attendee = registered(ATTENDEE)

        assert_error(login(attendee["email"], DEFAULT_PASSWORD, ORGANIZER), 401, "QIT002001")

    def test_same_email_in_two_roles_logs_into_each_role_separately(self):
        shared_email = new_email()
        as_attendee = registered(ATTENDEE, email=shared_email, password="senha-do-publico-1")
        as_organizer = registered(ORGANIZER, email=shared_email, password="senha-do-organizador-1")

        attendee_login = login(shared_email, "senha-do-publico-1", ATTENDEE)
        organizer_login = login(shared_email, "senha-do-organizador-1", ORGANIZER)
        crossed_login = login(shared_email, "senha-do-publico-1", ORGANIZER)

        assert attendee_login.json()["id"] == as_attendee["id"]
        assert organizer_login.json()["id"] == as_organizer["id"]
        assert_error(crossed_login, 401, "QIT002001")

    def test_unknown_user_type_is_refused(self):
        user = registered(ATTENDEE)

        assert_error(login(user["email"], DEFAULT_PASSWORD, "admin"), 400, "QIT000001")

    def test_missing_password_is_refused(self):
        response = users.send("POST", "/internal/login", json={"email": new_email(), "user_type": ATTENDEE})

        assert_error(response, 400, "QIT000001")

    def test_without_token_is_refused(self):
        response = users.send(
            "POST",
            "/internal/login",
            json={"email": new_email(), "password": DEFAULT_PASSWORD, "user_type": ATTENDEE},
            token=None,
        )

        assert_error(response, 403, "QIT000002")

    def test_token_of_another_api_is_refused(self):
        response = users.send(
            "POST",
            "/internal/login",
            json={"email": new_email(), "password": DEFAULT_PASSWORD, "user_type": ATTENDEE},
            token=payments.token,
        )

        assert_error(response, 403, "QIT000002")
