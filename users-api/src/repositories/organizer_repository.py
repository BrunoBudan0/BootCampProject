from uuid import uuid4

from database import Context
from models import Organizer


class OrganizerRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create_organizer(self, name, email, document, password_hash, phone):
        organizer = Organizer(
            organizer_key=uuid4(),
            name=name,
            email=email,
            document=document,
            password_hash=password_hash,
            phone=phone,
        )

        self.session.add(organizer)
        self.session.flush()

        return organizer

    def get_organizer_by_email(self, email):
        return self.session.query(Organizer).filter_by(email=email).first()

    def get_organizer_by_key(self, organizer_key):
        return self.session.query(Organizer).filter_by(organizer_key=organizer_key).first()
