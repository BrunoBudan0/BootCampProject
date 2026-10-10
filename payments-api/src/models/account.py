from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base

class Account(Base):
    __tablename__ = "account"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_key = Column(UUID(as_uuid=True), nullable=False)
    event_id = Column(UUID(as_uuid=True), nullable=False)  # REF: API de Eventos
    holder_id = Column(UUID(as_uuid=True), nullable=True)  # REF: API de Usuários; NULL em fee e external
    kind = Column(String(10), nullable=False)
    balance_cents = Column(BigInteger, nullable=False, default=0)
    blocked = Column(Boolean, nullable=False, default=False)
    idempotency_key = Column(String(80), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("account_key", name="uq_account_key"),
        UniqueConstraint("idempotency_key", name="uq_account_idempotency_key"),
    )

    USER_KIND = "user"
    FEE_KIND = "fee"
    EXTERNAL_KIND = "external"
