from sqlalchemy import select
from sqlalchemy.orm import Session

from models import CashbackRate, Event, FeeRate


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, *rows) -> None:
        self.session.add_all(rows)
        self.session.flush()

    def get_by_id(self, event_id):
        return self.session.get(Event, event_id)

    def get_for_update(self, event_id):
        # trava o evento: duas mudanças de taxa no mesmo evento fazem fila
        query = select(Event).where(Event.id == event_id).with_for_update()
        return self.session.scalars(query).first()

    def list(self, limit: int, page: int) -> tuple[list[Event], bool]:
        # busca um a mais só pra saber se tem próxima página
        query = (
            select(Event)
            .order_by(Event.created_at.desc(), Event.id)
            .limit(limit + 1)
            .offset((page - 1) * limit)
        )
        rows = list(self.session.scalars(query))
        return rows[:limit], len(rows) <= limit

    def current_fee_rate(self, event_id) -> FeeRate:
        return self._current(FeeRate, event_id)

    def current_cashback_rate(self, event_id) -> CashbackRate:
        return self._current(CashbackRate, event_id)

    def _current(self, model, event_id):
        # todo evento nasce com tarifa e cashback; faltar é bug, e o one() estoura
        query = (
            select(model)
            .where(model.event_id == event_id)
            .order_by(model.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(query).one()

    def list_cashback_rates(self, event_id):
        query = (
            select(CashbackRate)
            .where(CashbackRate.event_id == event_id)
            .order_by(CashbackRate.created_at.desc())
        )
        return self.session.scalars(query).all()