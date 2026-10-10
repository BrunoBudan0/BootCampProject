from models import CashbackRate, Event, FeeRate


def event_to_dict(event: Event, fee_rate: FeeRate, cashback_rate: CashbackRate) -> dict:
    return {
        "id": str(event.id),
        "organizer_id": str(event.organizer_id),
        "name": event.name,
        "location": event.location,
        "description": event.description,
        "active": event.active,
        "fee_rate_bps": fee_rate.rate_bps,
        "cashback_rate_bps": cashback_rate.rate_bps,
        "created_at": event.created_at.isoformat(),
    }


def event_summary_to_dict(event: Event) -> dict:
    return {
        "id": str(event.id),
        "name": event.name,
        "location": event.location,
        "active": event.active,
        "created_at": event.created_at.isoformat(),
    }