from models import EventAttendee, EventCompany


def stand_to_dict(stand: EventCompany) -> dict:
    return {
        "id": str(stand.id),
        "event_id": str(stand.event_id),
        "company_id": str(stand.company_id),
        "stand_name": stand.stand_name,
        "account_id": str(stand.account_id),
        "created_at": stand.created_at.isoformat(),
    }


def credential_to_dict(credential: EventAttendee) -> dict:
    return {
        "id": str(credential.id),
        "event_id": str(credential.event_id),
        "attendee_id": str(credential.attendee_id),
        "account_id": str(credential.account_id),
        "blocked": credential.blocked,
        "created_at": credential.created_at.isoformat(),
    }