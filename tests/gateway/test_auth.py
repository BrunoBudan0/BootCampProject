import uuid

from tests.gateway.helpers import User, login, new_email, signup
from tests.utils.services import gateway


class TestLogin:
    def test_login_returns_a_token_that_opens_me(self):
        user = User("attendee")

        response = user.send("GET", "/me")

        assert response.status_code == 200
        assert response.json()["id"] == user.id

    def test_wrong_password(self):
        email, _ = signup("organizer")

        response = login(email, "organizer", password="senha-errada-1")

        assert response.status_code == 401
        assert response.json()["code"] == "QIT002001"

    def test_unknown_email_gets_the_same_answer(self):
        response = login(new_email("ninguem"), "attendee")

        assert response.status_code == 401
        assert response.json()["code"] == "QIT002001"

    def test_each_login_gets_a_new_token(self):
        first = User("company")
        second_login = login(first.email, "company").json()

        assert second_login["token"] != first.token

    def test_too_many_attempts_on_the_same_email(self):
        email = new_email("forca-bruta")
        answers = [login(email, "attendee", password=f"tentativa-{i}").status_code for i in range(11)]

        assert answers[:10] == [401] * 10
        assert answers[10] == 429


class TestSession:
    def test_protected_route_without_auth_token(self):
        response = gateway.send("GET", "/me")

        assert response.status_code == 401
        assert response.json()["code"] == "QIT002002"

    def test_invented_auth_token(self):
        response = gateway.send("GET", "/me", headers={"AUTH-TOKEN": uuid.uuid4().hex})

        assert response.status_code == 401
        assert response.json()["code"] == "QIT002002"

    def test_app_cannot_choose_who_it_is(self):
        user = User("attendee")
        someone_else = User("attendee")

        response = user.send("GET", "/me", headers={"X-User-Id": someone_else.id, "X-User-Type": "organizer"})

        assert response.status_code == 200
        assert response.json()["id"] == user.id

    def test_signup_does_not_need_a_session(self):
        email, user_id = signup("organizer")

        assert user_id
