from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from errors import AttendeeAlreadyInEvent
from models import EventAttendee


class EventAttendeeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, event_attendee_id):
        return self.session.get(EventAttendee, event_attendee_id)

    def find(self, event_id, attendee_id):
        query = select(EventAttendee).where(
            EventAttendee.event_id == event_id,
            EventAttendee.attendee_id == attendee_id,
        )
        return self.session.scalars(query).first()

    def add(self, credential: EventAttendee) -> None:
        self.session.add(credential)
        try:
            self.session.flush()
        except IntegrityError as error:
            self.session.rollback()
            if "uq_event_attendee" in str(error.orig):
                raise AttendeeAlreadyInEvent()
            raise