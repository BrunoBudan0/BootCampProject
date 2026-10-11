from controllers.base_controller import BaseController
from dtos import AttendeeDTO, CompanyDTO, OrganizerDTO
from errors import InvalidCredentials, NotAuthenticated, NotFoundCompany
from models import Attendee, Company, Organizer
from repositories import AttendeeRepository, CompanyRepository, OrganizerRepository
from utils.identifiers import parse_uuid_or_none
from utils.password import PASSWORD_HASH_OF_NOBODY, password_matches

DTO_BY_USER_TYPE = {
    Attendee.USER_TYPE: AttendeeDTO,
    Organizer.USER_TYPE: OrganizerDTO,
    Company.USER_TYPE: CompanyDTO,
}


class UserController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        attendee_repository = AttendeeRepository(self.context)
        organizer_repository = OrganizerRepository(self.context)
        self.company_repository = CompanyRepository(self.context)

        self.find_user_by_email = {
            Attendee.USER_TYPE: attendee_repository.get_attendee_by_email,
            Organizer.USER_TYPE: organizer_repository.get_organizer_by_email,
            Company.USER_TYPE: self.company_repository.get_company_by_email,
        }
        self.find_user_by_key = {
            Attendee.USER_TYPE: attendee_repository.get_attendee_by_key,
            Organizer.USER_TYPE: organizer_repository.get_organizer_by_key,
            Company.USER_TYPE: self.company_repository.get_company_by_key,
        }

    def login(self, payload: dict) -> dict:
        user_type = payload["user_type"]
        user = self.find_user_by_email[user_type](payload["email"].lower())

        stored_password_hash = user.password_hash if user is not None else PASSWORD_HASH_OF_NOBODY
        password_is_right = password_matches(payload["password"], stored_password_hash)

        if user is None or not password_is_right:
            raise InvalidCredentials()

        user_dto = DTO_BY_USER_TYPE[user_type].obj_to_dict(user)
        self.logger.info(f"Login of {user_type} {user_dto['id']}")
        return user_dto

    def get_caller(self) -> dict:
        caller_id = self.context.caller_id
        caller_type = self.context.caller_type

        if caller_id is None or caller_type not in self.find_user_by_key:
            raise NotAuthenticated()

        caller = self.find_user_by_key[caller_type](caller_id)
        if caller is None:
            raise NotAuthenticated()

        return DTO_BY_USER_TYPE[caller_type].obj_to_dict(caller)

    def get_company_names(self, company_id: str) -> dict:
        company_key = parse_uuid_or_none(company_id)
        company = None
        if company_key is not None:
            company = self.company_repository.get_company_by_key(company_key)

        if company is None:
            raise NotFoundCompany(company_id)

        return CompanyDTO.names_to_dict(company)