import uuid

from controllers.base_controller import BaseController
from dtos import receipt_to_dict
from errors import (
    CredentialBlocked,
    CredentialNotFound,
    EventClosed,
    InsufficientStock,
    NotAllowedForUserType,
    ProductInactive,
    ProductNotFound,
)
from models import Purchase, PurchaseStatus, UserType
from repositories import (
    EventAttendeeRepository,
    EventCompanyRepository,
    EventRepository,
    PurchaseRepository,
)
from utils.purchase_math import calculate, normalize_cart


class PurchaseController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.events = EventRepository(self.session)
        self.stands = EventCompanyRepository(self.session)
        self.credentials = EventAttendeeRepository(self.session)
        self.purchases = PurchaseRepository(self.session)

    def create_purchase(self, user_id: uuid.UUID, user_type: str, payload: dict) -> dict:
        if user_type != UserType.ATTENDEE.value:
            raise NotAllowedForUserType()

        credential = self.credentials.get_by_id(uuid.UUID(payload["event_attendee_id"]))
        if credential is None or credential.attendee_id != user_id:
            raise CredentialNotFound()
        if credential.blocked:
            raise CredentialBlocked()

        stand = self.stands.get_by_id(uuid.UUID(payload["event_company_id"]))
        if stand is None or stand.event_id != credential.event_id:
            raise ProductNotFound()

        event = self.events.get_by_id(credential.event_id)
        if not event.active:
            raise EventClosed()

        cart = normalize_cart(payload["items"])
        self._check_products(cart, stand.id)

        # baixa na ordem do id: duas compras dos mesmos produtos não se travam
        lines = []
        for line in cart:
            priced = self.purchases.reserve(stand.id, line)
            if priced is None:
                # desativaram no meio do caminho, ou acabou o estoque
                still_active = self.purchases.is_active(line.product_id)
                self.session.rollback()
                raise InsufficientStock() if still_active else ProductInactive()
            lines.append(priced)

        fee_rate = self.events.current_fee_rate(event.id)
        cashback_rate = self.events.current_cashback_rate(event.id)
        amounts = calculate(lines, fee_rate.rate_bps, cashback_rate.rate_bps)

        purchase = Purchase(
            id=uuid.uuid4(),
            event_attendee_id=credential.id,
            event_company_id=stand.id,
            status=PurchaseStatus.PENDING.value,
            total_cents=amounts.total_cents,
            fee_rate_id=fee_rate.id,
            fee_cents=amounts.fee_cents,
            cashback_rate_id=cashback_rate.id,
            cashback_cents=amounts.cashback_cents,
            idempotency_key=payload["idempotency_key"],
        )
        items = self.purchases.add(purchase, lines)
        self.session.commit()

        self.logger.info(f"compra {purchase.id} reservada: {amounts.total_cents} centavos")
        return receipt_to_dict(purchase, items, stand)

    def _check_products(self, cart, stand_id) -> None:
        products = self.purchases.products_of_cart(cart)
        for line in cart:
            product = products.get(line.product_id)
            if product is None or product.event_company_id != stand_id:
                raise ProductNotFound()
            if not product.active:
                raise ProductInactive()