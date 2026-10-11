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
from errors import QIException
from models import CriticalLogType, EventAttendee, EventCompany, UserType
from repositories import EventAttendeeRepository, EventCompanyRepository, EventRepository
from utils.critical_log import critical_log


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
            event_id, "user", f"acct:{event_id}:{company_id}", holder_id=company_id, holder_type="company"
        )

        stand = EventCompany(
            event_id=event_id,
            company_id=company_id,
            stand_name=payload["stand_name"],
            account_id=account_id,
        )
        self._save(stand, self.stands.add, account_id, user_id)

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
            event_id, "user", f"acct:{event_id}:{user_id}", holder_id=user_id, holder_type="attendee"
        )

        credential = EventAttendee(event_id=event_id, attendee_id=user_id, account_id=account_id)
        self._save(credential, self.credentials.add, account_id, user_id)

        return credential_to_dict(credential)

    def _save(self, row, add, account_id, user_id) -> None:
        try:
            add(row)
            self.session.commit()
        except QIException:
            # empresa ou pessoa repetida: a chave devolveu a mesma conta, não sobra nada solto
            raise
        except Exception:
            self.session.rollback()
            critical_log(
                CriticalLogType.ORPHAN_ACCOUNT,
                "conta criada em Pagamentos, mas o stand ou a credencial não foi gravado",
                account_id=account_id,
                user_id=user_id,
            )
            raise
