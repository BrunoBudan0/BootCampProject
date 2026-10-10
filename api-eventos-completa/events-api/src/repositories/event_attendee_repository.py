from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from errors import AttendeeAlreadyInEvent
from models import EventAttendee


class EventAttendeeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, event_attendee_id) -> EventAttendee | None:
        return self.session.get(EventAttendee, event_attendee_id)

    def set_blocked(self, credential: EventAttendee, blocked: bool) -> bool:
        # devolve se mudou de verdade: bloquear o que já está bloqueado não é evento
        query = (
            update(EventAttendee)
            .where(EventAttendee.id == credential.id, EventAttendee.blocked.is_not(blocked))
            .values(blocked=blocked)
            .returning(EventAttendee.id)
            .execution_options(synchronize_session=False)
        )
        changed = self.session.execute(query).first() is not None
        if changed:
            self.session.refresh(credential)
        return changed

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
