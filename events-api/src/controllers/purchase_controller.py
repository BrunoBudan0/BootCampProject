import uuid

from connectors import PaymentsConnector
from controllers.base_controller import BaseController
from dtos import receipt_to_dict
from errors import (
    CredentialBlocked,
    CredentialNotFound,
    EventClosed,
    IdempotencyKeyReused,
    InsufficientBalance,
    InsufficientStock,
    NotAllowedForUserType,
    ProductInactive,
    ProductNotFound,
    PurchaseNotFound,
    UpstreamUnavailable,
)
from models import Purchase, PurchaseStatus, UserType
from repositories import (
    EventAttendeeRepository,
    EventCompanyRepository,
    EventRepository,
    KeyAlreadyUsed,
    PurchaseRepository,
)
from utils.purchase_math import PurchaseAmounts, calculate, normalize_cart, purchase_legs


class PurchaseController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.events = EventRepository(self.session)
        self.stands = EventCompanyRepository(self.session)
        self.credentials = EventAttendeeRepository(self.session)
        self.purchases = PurchaseRepository(self.session)
        self.payments = PaymentsConnector()

    def create_purchase(self, user_id: uuid.UUID, user_type: str, payload: dict) -> tuple[dict, bool]:
        if user_type != UserType.ATTENDEE.value:
            raise NotAllowedForUserType()

        cart = normalize_cart(payload["items"])
        key = payload["idempotency_key"]

        existing = self.purchases.get_by_key(key)
        if existing is not None:
            return self._replay(existing, user_id, payload, cart), False

        credential = self.credentials.get_by_id(uuid.UUID(payload["event_attendee_id"]))
        if credential is None or credential.attendee_id != user_id:
            raise CredentialNotFound()
        if credential.blocked:
            raise CredentialBlocked()

        stand = self.stands.get_by_id(uuid.UUID(payload["event_company_id"]))
        if stand is None or stand.event_id != credential.event_id:
            raise ProductNotFound()

        event = self.events.get_by_id(credential.event_id)
        if event is None or not event.active:
            raise EventClosed()

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
            idempotency_key=key,
        )
        try:
            self.purchases.add(purchase, lines)
        except KeyAlreadyUsed:
            # outra requisição com a mesma chave gravou primeiro; o rollback devolveu o estoque
            existing = self.purchases.get_by_key(key)
            return self._replay(existing, user_id, payload, cart), False

        # a reserva fica gravada ANTES de chamar Pagamentos
        self.session.commit()
        self.logger.info(f"compra {purchase.id} reservada: {amounts.total_cents} centavos")

        return self.settle(purchase.id), True

    def settle(self, purchase_id: uuid.UUID) -> dict:
        purchase = self.purchases.get_by_id(purchase_id)
        if purchase is None:
            raise PurchaseNotFound()
        if purchase.status != PurchaseStatus.PENDING.value:
            return self._receipt(purchase)

        credential = self.credentials.get_by_id(purchase.event_attendee_id)
        stand = self.stands.get_by_id(purchase.event_company_id)
        event = self.events.get_by_id(stand.event_id) if stand else None
        if credential is None or stand is None or event is None:
            raise PurchaseNotFound()

        amounts = PurchaseAmounts(purchase.total_cents, purchase.fee_cents, purchase.cashback_cents)
        legs = purchase_legs(amounts, credential.account_id, stand.account_id, event.fee_account_id)

        # nenhuma transação de banco aberta durante a chamada HTTP
        self.session.rollback()
        result = self.payments.transfer(
            f"purchase:{purchase_id}",
            "balance",
            [(leg.source_account_id, leg.destination_account_id, leg.amount_cents) for leg in legs],
        )

        if result.outcome == "done":
            fee_transaction = next(
                (tx["id"] for leg, tx in zip(legs, result.transactions) if leg.name == "fee"), None
            )
            self.purchases.mark_paid(purchase, fee_transaction)
            self.session.commit()
            self.logger.info(f"compra {purchase_id} paga")
            return self._receipt(purchase)

        if result.outcome == "refused":
            self.purchases.cancel(purchase_id)
            self.session.commit()
            self.logger.info(f"compra {purchase_id} cancelada por Pagamentos: {result.code}")
            if result.code == "QIT002021":
                raise InsufficientBalance()
            if result.code == "QIT002022":
                raise CredentialBlocked()
            self.logger.error(f"recusa inesperada de Pagamentos na compra {purchase_id}: {result.code}")
            raise UpstreamUnavailable()

        # não sabemos se o dinheiro andou: a compra fica pending, e o reenvio tenta de novo
        self.logger.error(f"compra {purchase_id} sem resposta de Pagamentos, segue pending")
        raise UpstreamUnavailable()

    def _replay(self, purchase: Purchase, user_id, payload: dict, cart) -> dict:
        credential = self.credentials.get_by_id(purchase.event_attendee_id)
        items = self.purchases.items_of(purchase.id)

        same = (
            credential is not None
            and credential.attendee_id == user_id
            and str(purchase.event_attendee_id) == payload["event_attendee_id"].lower()
            and str(purchase.event_company_id) == payload["event_company_id"].lower()
            and [(i.product_id, i.quantity) for i in items] == [(l.product_id, l.quantity) for l in cart]
        )
        if not same:
            raise IdempotencyKeyReused()

        self.logger.info(f"reenvio da compra {purchase.id}, nada foi cobrado de novo")
        if purchase.status == PurchaseStatus.PENDING.value:
            return self.settle(purchase.id)
        return self._receipt(purchase)

    def _receipt(self, purchase: Purchase) -> dict:
        items = self.purchases.items_of(purchase.id)
        return receipt_to_dict(purchase, items, self.stands.get_by_id(purchase.event_company_id))

    def _check_products(self, cart, stand_id) -> None:
        products = self.purchases.products_of_cart(cart)
        for line in cart:
            product = products.get(line.product_id)
            if product is None or product.event_company_id != stand_id:
                raise ProductNotFound()
            if not product.active:
                raise ProductInactive()