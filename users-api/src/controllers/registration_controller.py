from sqlalchemy.exc import IntegrityError

from controllers.base_controller import BaseController
from dtos import AttendeeDTO, CompanyDTO, OrganizerDTO
from errors import DocumentAlreadyRegistered, EmailAlreadyRegistered, InvalidBirthDate, InvalidDocument
from models import Attendee, Company, Organizer
from repositories import AttendeeRepository, CompanyRepository, OrganizerRepository
from utils.birth_date import age_in_years, parse_calendar_date, today_in_sao_paulo
from utils.document_number import document_kind, is_valid_cnpj, is_valid_cpf, is_valid_cpf_or_cnpj
from utils.integrity_error import violated_constraint_name
from utils.password import hash_password

MINIMUM_ATTENDEE_AGE = 18
EMAIL_CONSTRAINTS = {"uq_attendee_email", "uq_organizer_email", "uq_company_email"}
DOCUMENT_CONSTRAINTS = {"uq_attendee_document", "uq_organizer_document", "uq_company_document"}


class RegistrationController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.attendee_repository = AttendeeRepository(self.context)
        self.organizer_repository = OrganizerRepository(self.context)
        self.company_repository = CompanyRepository(self.context)

    def register_attendee(self, payload: dict) -> dict:
        if not is_valid_cpf(payload["document"]):
            raise InvalidDocument("CPF")

        birth_date = self._birth_date_or_refuse(payload["birth_date"])

        try:
            attendee = self.attendee_repository.create_attendee(
                name=payload["name"],
                email=payload["email"].lower(),
                document=payload["document"],
                password_hash=hash_password(payload["password"]),
                birth_date=birth_date,
                phone=payload.get("phone"),
                postal_code=payload.get("postal_code"),
            )
        except IntegrityError as integrity_error:
            self.session.rollback()
            self._refuse_if_already_registered(integrity_error, Attendee.USER_TYPE)
            raise

        attendee_dto = AttendeeDTO.obj_to_dict(attendee)
        self.session.commit()
        self.logger.info(f"Attendee registered: {attendee_dto['id']}")
        return attendee_dto

    def register_organizer(self, payload: dict) -> dict:
        if not is_valid_cpf_or_cnpj(payload["document"]):
            raise InvalidDocument(document_kind(payload["document"]))

        try:
            organizer = self.organizer_repository.create_organizer(
                name=payload["name"],
                email=payload["email"].lower(),
                document=payload["document"],
                password_hash=hash_password(payload["password"]),
                phone=payload.get("phone"),
            )
        except IntegrityError as integrity_error:
            self.session.rollback()
            self._refuse_if_already_registered(integrity_error, Organizer.USER_TYPE)
            raise

        organizer_dto = OrganizerDTO.obj_to_dict(organizer)
        self.session.commit()
        self.logger.info(f"Organizer registered: {organizer_dto['id']}")
        return organizer_dto

    def register_company(self, payload: dict) -> dict:
        if not is_valid_cnpj(payload["document"]):
            raise InvalidDocument("CNPJ")

        try:
            company = self.company_repository.create_company(
                legal_name=payload["legal_name"],
                trade_name=payload["trade_name"],
                email=payload["email"].lower(),
                document=payload["document"],
                password_hash=hash_password(payload["password"]),
                phone=payload.get("phone"),
            )
        except IntegrityError as integrity_error:
            self.session.rollback()
            self._refuse_if_already_registered(integrity_error, Company.USER_TYPE)
            raise

        company_dto = CompanyDTO.obj_to_dict(company)
        self.session.commit()
        self.logger.info(f"Company registered: {company_dto['id']}")
        return company_dto

    def _birth_date_or_refuse(self, raw_birth_date: str):
        birth_date = parse_calendar_date(raw_birth_date)
        if birth_date is None:
            raise InvalidBirthDate("the date does not exist")

        today = today_in_sao_paulo()
        if birth_date > today:
            raise InvalidBirthDate("the date is in the future")

        if age_in_years(birth_date, today) < MINIMUM_ATTENDEE_AGE:
            raise InvalidBirthDate(f"younger than {MINIMUM_ATTENDEE_AGE}")

        return birth_date

    def _refuse_if_already_registered(self, integrity_error, user_type: str) -> None:
        constraint_name = violated_constraint_name(integrity_error)

        if constraint_name in EMAIL_CONSTRAINTS:
            raise EmailAlreadyRegistered(user_type)

        if constraint_name in DOCUMENT_CONSTRAINTS:
            raise DocumentAlreadyRegistered(user_type)