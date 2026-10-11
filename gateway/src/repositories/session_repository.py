from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from models import Session


class SessionRepository:
    def __init__(self, session: DbSession) -> None:
        self.session = session

    def add(self, row: Session) -> None:
        self.session.add(row)
        self.session.flush()

    def find_valid(self, token_hash: str, now: datetime) -> Session | None:
        query = select(Session).where(Session.token_hash == token_hash, Session.expires_at > now)
        return self.session.scalars(query).first()
