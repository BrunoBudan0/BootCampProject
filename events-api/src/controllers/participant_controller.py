import uuid

from connectors import PaymentsConnector, UsersConnector
from controllers.base_controller import BaseController
from dtos import credential_to_dict, stand_to_dict
from errors import (
    AttendeeAlreadyInEvent,
    CompanyAlreadyInEvent,
    EventClosed,
    EventNotFound,
    NotAllowedForUserType,
)
from models import EventAttendee, EventCompany, UserType
from repositories import EventAttendeeRepository, EventCompanyRepository, EventRepository


class ParticipantController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.events = EventRepository(self.session)
        self.stands = EventCompanyRepository(self.session)
        self.credentials = EventAttendeeRepository(self.session)
        self.payments = PaymentsConnector()
        self.users = UsersConnector()

    def add_company(self, user_id: uuid.UUID, user_type: str, event_id: uuid.UUID, payload: dict) -> dict:
        if user_type != UserType.ORGANIZER.value:
            raise NotAllowedForUserType()

        event = self.events.get_by_id(event_id)
        if event is None or event.organizer_id != user_id:
            raise EventNotFound()
        if not event.active:
            raise EventClosed()

        company_id = uuid.UUID(payload["company_id"])
        if self.stands.find(event_id, company_id):
            raise CompanyAlreadyInEvent()

        # fecha a transação de leitura antes de chamar outro serviço
        self.session.rollback()

        self.users.ensure_company_exists(company_id)
        account_id = self.payments.create_account(
            event_id, company_id, "user", f"account:{event_id}:{company_id}"
        )

        stand = EventCompany(
            event_id=event_id,
            company_id=company_id,
            stand_name=payload["stand_name"],
            account_id=account_id,
        )
        self.stands.add(stand)
        self.session.commit()

        return stand_to_dict(stand)

    def add_attendee(self, user_id: uuid.UUID, user_type: str, event_id: uuid.UUID) -> dict:
        if user_type != UserType.ATTENDEE.value:
            raise NotAllowedForUserType()

        event = self.events.get_by_id(event_id)
        if event is None:
            raise EventNotFound()
        if not event.active:
            raise EventClosed()

        if self.credentials.find(event_id, user_id):
            raise AttendeeAlreadyInEvent()

        self.session.rollback()

        account_id = self.payments.create_account(
            event_id, user_id, "user", f"account:{event_id}:{user_id}"
        )

        credential = EventAttendee(event_id=event_id, attendee_id=user_id, account_id=account_id)
        self.credentials.add(credential)
        self.session.commit()

        return credential_to_dict(credential)