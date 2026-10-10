from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from errors import CompanyAlreadyInEvent
from models import EventCompany


class EventCompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, event_company_id):
        return self.session.get(EventCompany, event_company_id)

    def find(self, event_id, company_id):
        query = select(EventCompany).where(
            EventCompany.event_id == event_id,
            EventCompany.company_id == company_id,
        )
        return self.session.scalars(query).first()

    def add(self, stand: EventCompany) -> None:
        self.session.add(stand)
        try:
            self.session.flush()
        except IntegrityError as error:
            self.session.rollback()
            if "uq_event_company" in str(error.orig):
                raise CompanyAlreadyInEvent()
            raise