import uuid

from controllers.base_controller import BaseController
from dtos import rate_to_dict
from errors import CashbackAboveFee, EventNotFound
from models import CashbackRate, FeeRate, UserType
from repositories import EventAttendeeRepository, EventCompanyRepository, EventRepository


class RateController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.events = EventRepository(self.session)
        self.stands = EventCompanyRepository(self.session)
        self.credentials = EventAttendeeRepository(self.session)

    def change_fee_rate(self, user_id: uuid.UUID, user_type: str, event_id: uuid.UUID, payload: dict) -> dict:
        event = self._owned_event_locked(user_id, user_type, event_id)

        cashback = self.events.current_cashback_rate(event.id)
        if payload["rate_bps"] < cashback.rate_bps:
            raise CashbackAboveFee()

        rate = FeeRate(
            event_id=event.id,
            rate_bps=payload["rate_bps"],
            reason=payload["reason"].strip(),
            organizer_id=user_id,
        )
        self.events.add(rate)
        self.session.commit()

        self.logger.info(f"tarifa do evento {event.id} agora {rate.rate_bps} bps")
        return rate_to_dict(rate, current=True)

    def change_cashback_rate(self, user_id: uuid.UUID, user_type: str, event_id: uuid.UUID, payload: dict) -> dict:
        event = self._owned_event_locked(user_id, user_type, event_id)

        fee = self.events.current_fee_rate(event.id)
        if payload["rate_bps"] > fee.rate_bps:
            raise CashbackAboveFee()

        rate = CashbackRate(
            event_id=event.id,
            rate_bps=payload["rate_bps"],
            reason=payload["reason"].strip(),
            organizer_id=user_id,
        )
        self.events.add(rate)
        self.session.commit()

        self.logger.info(f"cashback do evento {event.id} agora {rate.rate_bps} bps")
        return rate_to_dict(rate, current=True)

    def list_cashback_rates(self, user_id: uuid.UUID, user_type: str, event_id: uuid.UUID) -> dict:
        event = self.events.get_by_id(event_id)
        if event is None or not self._takes_part(user_id, user_type, event):
            raise EventNotFound()

        rates = self.events.list_cashback_rates(event_id)
        return {"data": [rate_to_dict(rate, current=(i == 0)) for i, rate in enumerate(rates)]}

    def _owned_event_locked(self, user_id, user_type, event_id):
        if user_type != UserType.ORGANIZER.value:
            raise EventNotFound()

        event = self.events.get_for_update(event_id)
        if event is None or event.organizer_id != user_id:
            raise EventNotFound()
        return event

    def _takes_part(self, user_id, user_type, event) -> bool:
        if user_type == UserType.ORGANIZER.value:
            return event.organizer_id == user_id
        if user_type == UserType.COMPANY.value:
            return self.stands.find(event.id, user_id) is not None
        if user_type == UserType.ATTENDEE.value:
            return self.credentials.find(event.id, user_id) is not None
        return False
