def rate_to_dict(rate, current: bool = False) -> dict:
    return {
        "id": str(rate.id),
        "event_id": str(rate.event_id),
        "rate_bps": rate.rate_bps,
        "reason": rate.reason,
        "organizer_id": str(rate.organizer_id),
        "created_at": rate.created_at.isoformat(),
        "current": current,
    }
