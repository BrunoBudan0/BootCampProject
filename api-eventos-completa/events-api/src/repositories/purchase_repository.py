from datetime import datetime, timedelta, timezone

from sqlalchemy import func, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    CriticalLogEvent,
    EventCompany,
    FeeCharge,
    FeeChargeKind,
    FeeRate,
    Product,
    Purchase,
    PurchaseProduct,
    PurchaseStatus,
)
from utils.purchase_math import CartLine, PricedLine


class KeyAlreadyUsed(Exception):
    pass


class StockCheckTriggered(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PurchaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, purchase_id) -> Purchase | None:
        return self.session.get(Purchase, purchase_id)

    def get_by_key(self, idempotency_key: str) -> Purchase | None:
        return self.session.scalars(
            select(Purchase).where(Purchase.idempotency_key == idempotency_key)
        ).first()

    def items_of(self, purchase_id) -> list[PurchaseProduct]:
        query = (
            select(PurchaseProduct)
            .where(PurchaseProduct.purchase_id == purchase_id)
            .order_by(PurchaseProduct.product_id)
        )
        return list(self.session.scalars(query))

    def products_of_cart(self, cart: list[CartLine]) -> dict:
        ids = [line.product_id for line in cart]
        rows = self.session.scalars(select(Product).where(Product.id.in_(ids)))
        return {product.id: product for product in rows}

    def reserve(self, event_company_id, line: CartLine) -> PricedLine | None:
        # baixa só se tiver estoque; null = sem controle de estoque
        query = (
            update(Product)
            .where(
                Product.id == line.product_id,
                Product.event_company_id == event_company_id,
                Product.active.is_(True),
                Product.stock.is_(None) | (Product.stock >= line.quantity),
            )
            .values(stock=Product.stock - line.quantity)
            .returning(Product.name, Product.price_cents)
            .execution_options(synchronize_session=False)
        )
        try:
            row = self.session.execute(query).first()
        except IntegrityError as error:
            # o CHECK de estoque só barra se o WHERE acima tiver um bug
            self.session.rollback()
            if "ck_product_stock" in str(error.orig):
                raise StockCheckTriggered()
            raise
        if row is None:
            return None
        return PricedLine(line.product_id, row.name, row.price_cents, line.quantity)

    def is_active(self, product_id) -> bool:
        return bool(self.session.scalar(select(Product.active).where(Product.id == product_id)))

    def add(self, purchase: Purchase, lines: list[PricedLine]) -> list[PurchaseProduct]:
        items = [
            PurchaseProduct(
                purchase_id=purchase.id,
                product_id=line.product_id,
                product_name=line.product_name,
                unit_price_cents=line.unit_price_cents,
                quantity=line.quantity,
            )
            for line in lines
        ]
        self.session.add(purchase)
        try:
            self.session.flush()
        except IntegrityError as error:
            self.session.rollback()
            if "uq_purchase_idempotency" in str(error.orig):
                raise KeyAlreadyUsed()
            raise

        self.session.add_all(items)
        self.session.flush()
        return items

    def mark_paid(self, purchase: Purchase, fee_transaction_id) -> bool:
        changed = self._move_status(purchase.id, PurchaseStatus.PENDING, PurchaseStatus.PAID)
        if changed and purchase.fee_cents > 0:
            self.session.add(FeeCharge(
                purchase_id=purchase.id,
                fee_rate_id=purchase.fee_rate_id,
                kind=FeeChargeKind.CHARGE.value,
                base_cents=purchase.total_cents,
                amount_cents=purchase.fee_cents,
                transaction_id=fee_transaction_id,
            ))
            self.session.flush()
        return changed

    def cancel(self, purchase_id) -> bool:
        changed = self._move_status(purchase_id, PurchaseStatus.PENDING, PurchaseStatus.CANCELED)
        if changed:
            self._restock(purchase_id)
        return changed

    def mark_refunded(self, purchase: Purchase, reason: str, user_id, fee_transaction_id) -> bool:
        changed = self._move_status(
            purchase.id,
            PurchaseStatus.PAID,
            PurchaseStatus.REFUNDED,
            refund_reason=reason,
            refunded_by=user_id,
            refunded_at=_now(),
        )
        if not changed:
            return False

        self._restock(purchase.id)
        if purchase.fee_cents > 0:
            self.session.add(FeeCharge(
                purchase_id=purchase.id,
                fee_rate_id=purchase.fee_rate_id,
                kind=FeeChargeKind.REFUND.value,
                base_cents=purchase.total_cents,
                amount_cents=-purchase.fee_cents,
                transaction_id=fee_transaction_id,
            ))
        self.session.flush()
        return True

    def fee_transaction_of(self, purchase_id):
        return self.session.scalar(
            select(FeeCharge.transaction_id).where(
                FeeCharge.purchase_id == purchase_id,
                FeeCharge.kind == FeeChargeKind.CHARGE.value,
            )
        )

    def pending_ids(self, older_than_seconds: int, limit: int) -> list:
        limit_date = _now() - timedelta(seconds=older_than_seconds)
        query = (
            select(Purchase.id)
            .where(Purchase.status == PurchaseStatus.PENDING.value, Purchase.created_at < limit_date)
            .order_by(Purchase.created_at)
            .limit(limit)
        )
        return list(self.session.scalars(query))

    def has_critical_log(self, log_type: str, purchase_id) -> bool:
        query = select(CriticalLogEvent.id).where(
            CriticalLogEvent.type == log_type,
            CriticalLogEvent.purchase_id == purchase_id,
        )
        return self.session.scalar(query.limit(1)) is not None

    def fee_charges_of_event(self, event_id, limit: int, page: int):
        query = (
            select(FeeCharge, FeeRate.rate_bps)
            .join(Purchase, FeeCharge.purchase_id == Purchase.id)
            .join(EventCompany, Purchase.event_company_id == EventCompany.id)
            .join(FeeRate, FeeCharge.fee_rate_id == FeeRate.id)
            .where(EventCompany.event_id == event_id)
            .order_by(FeeCharge.created_at.desc(), FeeCharge.id)
            .limit(limit + 1)
            .offset((page - 1) * limit)
        )
        rows = list(self.session.execute(query).all())
        return rows[:limit], len(rows) <= limit

    def fee_net_of_event(self, event_id) -> int:
        query = (
            select(func.coalesce(func.sum(FeeCharge.amount_cents), 0))
            .join(Purchase, FeeCharge.purchase_id == Purchase.id)
            .join(EventCompany, Purchase.event_company_id == EventCompany.id)
            .where(EventCompany.event_id == event_id)
        )
        return int(self.session.scalar(query) or 0)

    def summary_of_event(self, event_id) -> dict:
        query = (
            select(Purchase.status, func.count(), func.coalesce(func.sum(Purchase.total_cents), 0))
            .join(EventCompany, Purchase.event_company_id == EventCompany.id)
            .where(EventCompany.event_id == event_id)
            .group_by(Purchase.status)
        )
        summary = {status.value: {"count": 0, "total_cents": 0} for status in PurchaseStatus}
        for status, count, total in self.session.execute(query).all():
            summary[status] = {"count": int(count), "total_cents": int(total)}
        return summary

    def _restock(self, purchase_id) -> None:
        for item in self.items_of(purchase_id):
            self.session.execute(
                update(Product)
                .where(Product.id == item.product_id, Product.stock.is_not(None))
                .values(stock=Product.stock + literal(item.quantity))
                .execution_options(synchronize_session=False)
            )

    def _move_status(self, purchase_id, current: PurchaseStatus, new: PurchaseStatus, **values) -> bool:
        # o WHERE no status atual faz a troca acontecer uma vez só, mesmo em paralelo
        query = (
            update(Purchase)
            .where(Purchase.id == purchase_id, Purchase.status == current.value)
            .values(status=new.value, updated_at=_now(), **values)
            .returning(Purchase.id)
            .execution_options(synchronize_session=False)
        )
        changed = self.session.execute(query).first() is not None
        if changed:
            # o objeto em memória precisa enxergar o que o UPDATE gravou
            purchase = self.session.get(Purchase, purchase_id)
            if purchase is not None:
                self.session.refresh(purchase)
        return changed
