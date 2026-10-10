from sqlalchemy.orm import Session
from models import EventCompany

class EventCompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, event_company_id):
        return self.session.get(EventCompany, event_company_id)