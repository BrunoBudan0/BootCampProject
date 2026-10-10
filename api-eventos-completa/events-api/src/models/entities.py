import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CHAR, BigInteger, Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# id gerado na aplicação: precisa existir antes do insert (chave de idempotência)
def _id():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _ref(nullable: bool = False):
    # uuid de outro serviço, sem FK
    return mapped_column(UUID(as_uuid=True), nullable=nullable)


def _fk(target: str, nullable: bool = False):
    return mapped_column(UUID(as_uuid=True), ForeignKey(target), nullable=nullable)


def _created_at():
    return mapped_column(DateTime, nullable=False, default=_now)


class Event(Base):
    __tablename__ = "event"

    id: Mapped[uuid.UUID] = _id()
    organizer_id: Mapped[uuid.UUID] = _ref()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fee_account_id: Mapped[uuid.UUID] = _ref()
    external_account_id: Mapped[uuid.UUID] = _ref()
    created_at: Mapped[datetime] = _created_at()


class FeeRate(Base):
    __tablename__ = "fee_rate"

    id: Mapped[uuid.UUID] = _id()
    event_id: Mapped[uuid.UUID] = _fk("event.id")
    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    organizer_id: Mapped[uuid.UUID] = _ref()
    created_at: Mapped[datetime] = _created_at()


class CashbackRate(Base):
    __tablename__ = "cashback_rate"

    id: Mapped[uuid.UUID] = _id()
    event_id: Mapped[uuid.UUID] = _fk("event.id")
    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    organizer_id: Mapped[uuid.UUID] = _ref()
    created_at: Mapped[datetime] = _created_at()


class EventCompany(Base):
    __tablename__ = "event_company"

    id: Mapped[uuid.UUID] = _id()
    event_id: Mapped[uuid.UUID] = _fk("event.id")
    company_id: Mapped[uuid.UUID] = _ref()
    stand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[uuid.UUID] = _ref()
    created_at: Mapped[datetime] = _created_at()


class EventAttendee(Base):
    __tablename__ = "event_attendee"

    id: Mapped[uuid.UUID] = _id()
    event_id: Mapped[uuid.UUID] = _fk("event.id")
    attendee_id: Mapped[uuid.UUID] = _ref()
    account_id: Mapped[uuid.UUID] = _ref()
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()


class Product(Base):
    __tablename__ = "product"

    id: Mapped[uuid.UUID] = _id()
    event_company_id: Mapped[uuid.UUID] = _fk("event_company.id")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    barcode: Mapped[str] = mapped_column(String(64), nullable=False)
    price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stock: Mapped[Optional[int]] = mapped_column(Integer)  # null = sem controle de estoque
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _created_at()


class Purchase(Base):
    __tablename__ = "purchase"

    id: Mapped[uuid.UUID] = _id()
    event_attendee_id: Mapped[uuid.UUID] = _fk("event_attendee.id")
    event_company_id: Mapped[uuid.UUID] = _fk("event_company.id")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_rate_id: Mapped[uuid.UUID] = _fk("fee_rate.id")
    fee_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cashback_rate_id: Mapped[uuid.UUID] = _fk("cashback_rate.id")
    cashback_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    refund_reason: Mapped[Optional[str]] = mapped_column(String(500))
    refunded_by: Mapped[Optional[uuid.UUID]] = _ref(nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now, onupdate=_now)


class PurchaseProduct(Base):
    __tablename__ = "purchase_product"

    id: Mapped[uuid.UUID] = _id()
    purchase_id: Mapped[uuid.UUID] = _fk("purchase.id")
    product_id: Mapped[uuid.UUID] = _fk("product.id")
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class FeeCharge(Base):
    __tablename__ = "fee_charge"

    id: Mapped[uuid.UUID] = _id()
    purchase_id: Mapped[uuid.UUID] = _fk("purchase.id")
    fee_rate_id: Mapped[uuid.UUID] = _fk("fee_rate.id")
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    base_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_id: Mapped[Optional[uuid.UUID]] = _ref(nullable=True)
    created_at: Mapped[datetime] = _created_at()


class CriticalLogEvent(Base):
    __tablename__ = "critical_log_event"

    id: Mapped[uuid.UUID] = _id()
    request_id: Mapped[Optional[str]] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    route: Mapped[Optional[str]] = mapped_column(String(120))
    http_status: Mapped[Optional[int]] = mapped_column(SmallInteger)
    error_code: Mapped[Optional[str]] = mapped_column(CHAR(9))
    user_id: Mapped[Optional[uuid.UUID]] = _ref(nullable=True)
    event_id: Mapped[Optional[uuid.UUID]] = _fk("event.id", nullable=True)
    event_attendee_id: Mapped[Optional[uuid.UUID]] = _fk("event_attendee.id", nullable=True)
    product_id: Mapped[Optional[uuid.UUID]] = _fk("product.id", nullable=True)
    purchase_id: Mapped[Optional[uuid.UUID]] = _fk("purchase.id", nullable=True)
    account_id: Mapped[Optional[uuid.UUID]] = _ref(nullable=True)
    amount_cents: Mapped[Optional[int]] = mapped_column(BigInteger)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = _created_at()
