import pytest

from tests.utils.payments import assert_error, new_uuid
from tests.utils.services import users
from tests.utils.users import ATTENDEE, COMPANY, ORGANIZER, PRIVATE_FIELDS, me, registered


@pytest.mark.parametrize("user_type", [ATTENDEE, ORGANIZER, COMPANY])
class TestMeOfEveryUserType:
    def test_caller_sees_own_registration(self, user_type):
        user = registered(user_type)

        response = me(user["id"], user_type)

        assert response.status_code == 200
        assert response.json()["id"] == user["id"]
        assert response.json()["user_type"] == user_type
        assert response.json()["email"] == user["email"]
        assert PRIVATE_FIELDS.isdisjoint(response.json())


class TestMeRefusals:
    def test_request_without_caller_is_not_authenticated(self):
        response = users.send("GET", "/me")

        assert_error(response, 401, "QIT002002")

    def test_unknown_caller_is_not_authenticated(self):
        assert_error(me(new_uuid(), ATTENDEE), 401, "QIT002002")

    def test_caller_type_must_match_the_table_of_the_caller(self):
        attendee = registered(ATTENDEE)

        assert_error(me(attendee["id"], ORGANIZER), 401, "QIT002002")

    def test_unknown_caller_type_is_not_authenticated(self):
        attendee = registered(ATTENDEE)

        assert_error(me(attendee["id"], "admin"), 401, "QIT002002")
