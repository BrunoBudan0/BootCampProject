from models import EventCompany, Purchase, PurchaseProduct


def receipt_to_dict(purchase: Purchase, items: list[PurchaseProduct], stand: EventCompany) -> dict:
    return {
        "id": str(purchase.id),
        "status": purchase.status,
        "event_id": str(stand.event_id),
        "event_attendee_id": str(purchase.event_attendee_id),
        "event_company_id": str(purchase.event_company_id),
        "stand_name": stand.stand_name,
        "items": [
            {
                "product_id": str(item.product_id),
                "product_name": item.product_name,
                "unit_price_cents": item.unit_price_cents,
                "quantity": item.quantity,
                "subtotal_cents": item.unit_price_cents * item.quantity,
            }
            for item in items
        ],
        "total_cents": purchase.total_cents,
        "fee_cents": purchase.fee_cents,
        "cashback_cents": purchase.cashback_cents,
        "paid_cents": purchase.total_cents - purchase.cashback_cents,
        "idempotency_key": purchase.idempotency_key,
        "refund": None if purchase.refunded_at is None else {
            "reason": purchase.refund_reason,
            "refunded_by": str(purchase.refunded_by),
            "refunded_at": purchase.refunded_at.isoformat(),
        },
        "created_at": purchase.created_at.isoformat(),
        "updated_at": purchase.updated_at.isoformat(),
    }
