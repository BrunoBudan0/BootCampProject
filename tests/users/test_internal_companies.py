from tests.utils.payments import assert_error, new_uuid
from tests.utils.services import users
from tests.utils.users import ATTENDEE, COMPANY, registered


def get_company(company_id, **send_options):
    return users.send("GET", f"/internal/companies/{company_id}", **send_options)


class TestInternalCompanyLookup:
    def test_existing_company_returns_its_names(self):
        company = registered(COMPANY)

        response = get_company(company["id"])

        assert response.status_code == 200
        assert response.json()["id"] == company["id"]
        assert response.json()["legal_name"] == company["legal_name"]
        assert response.json()["trade_name"] == company["trade_name"]

    def test_lookup_does_not_expose_contact_or_password(self):
        company = registered(COMPANY)

        body = get_company(company["id"]).json()

        assert {"password", "password_hash", "email", "document", "phone"}.isdisjoint(body)

    def test_unknown_company_is_not_found(self):
        assert_error(get_company(new_uuid()), 404, "QIT002009")

    def test_attendee_id_is_not_a_company(self):
        attendee = registered(ATTENDEE)

        assert_error(get_company(attendee["id"]), 404, "QIT002009")

    def test_malformed_id_is_not_found_instead_of_crashing(self):
        assert_error(get_company("not-a-uuid"), 404, "QIT002009")

    def test_without_token_is_refused(self):
        assert_error(get_company(new_uuid(), token=None), 403, "QIT000002")
