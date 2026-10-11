from uuid import uuid4

from database import Context
from models import Attendee


class AttendeeRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create_attendee(self, name, email, document, password_hash, birth_date, phone, postal_code):
        attendee = Attendee(
            attendee_key=uuid4(),
            name=name,
            email=email,
            document=document,
            password_hash=password_hash,
            birth_date=birth_date,
            phone=phone,
            postal_code=postal_code,
        )

        self.session.add(attendee)
        self.session.flush()

        return attendee

    def get_attendee_by_email(self, email):
        return self.session.query(Attendee).filter_by(email=email).first()

    def get_attendee_by_key(self, attendee_key):
        return self.session.query(Attendee).filter_by(attendee_key=attendee_key).first()
