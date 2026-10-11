import uuid

from connectors import PaymentsConnector
from controllers.base_controller import BaseController
from dtos import event_summary_to_dict, event_to_dict
from errors import CashbackAboveFee, EventNotFound, NotAllowedForUserType
from models import CashbackRate, CriticalLogType, Event, FeeRate, UserType
from repositories import EventRepository
from utils.critical_log import critical_log

INITIAL_RATE_REASON = "Taxa inicial do evento"


class EventController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.repository = EventRepository(self.session)
        self.payments = PaymentsConnector()

    def create_event(self, user_id: uuid.UUID, user_type: str, payload: dict) -> dict:
        if user_type != UserType.ORGANIZER.value:
            raise NotAllowedForUserType()

        fee_bps = payload["fee_rate_bps"]
        cashback_bps = payload["cashback_rate_bps"]
        if cashback_bps > fee_bps:
            raise CashbackAboveFee()

        event_id = uuid.uuid4()

        # contas primeiro, sem transação aberta; a chave deixa o reenvio seguro
        fee_account_id = self.payments.create_account(
            event_id, "fee", f"acct:{event_id}:fee"
        )
        external_account_id = self.payments.create_account(
            event_id, "external", f"acct:{event_id}:external"
        )

        event = Event(
            id=event_id,
            organizer_id=user_id,
            name=payload["name"],
            location=payload["location"],
            description=payload.get("description"),
            fee_account_id=fee_account_id,
            external_account_id=external_account_id,
        )
        fee_rate = FeeRate(
            event_id=event_id, rate_bps=fee_bps,
            reason=INITIAL_RATE_REASON, organizer_id=user_id,
        )
        cashback_rate = CashbackRate(
            event_id=event_id, rate_bps=cashback_bps,
            reason=INITIAL_RATE_REASON, organizer_id=user_id,
        )

        try:
            self.repository.add(event)
            self.repository.add(fee_rate, cashback_rate)
            self.session.commit()
        except Exception:
            self.session.rollback()
            for account_id in (fee_account_id, external_account_id):
                critical_log(
                    CriticalLogType.ORPHAN_ACCOUNT,
                    f"conta criada para o evento {event_id}, mas o evento não foi gravado",
                    account_id=account_id,
                    user_id=user_id,
                )
            raise

        self.logger.info(f"evento {event_id} criado")
        return event_to_dict(event, fee_rate, cashback_rate)

    def list_events(self, limit: int, page: int) -> dict:
        events, is_last_page = self.repository.list(limit, page)
        return {
            "data": [event_summary_to_dict(event) for event in events],
            "is_last_page": is_last_page,
        }

    def get_event(self, event_id: uuid.UUID) -> dict:
        event = self.repository.get_by_id(event_id)
        if event is None:
            raise EventNotFound()

        return event_to_dict(
            event,
            self.repository.current_fee_rate(event_id),
            self.repository.current_cashback_rate(event_id),
        )
