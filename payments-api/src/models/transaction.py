from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from models.base import Base

class Transaction(Base):
    __tablename__ = "transaction"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    transaction_key = Column(UUID(as_uuid=True), nullable=False)
    idempotency_key = Column(String(80), nullable=False)
    leg = Column(SmallInteger, nullable=False)
    source_account_id = Column(BigInteger, ForeignKey("account.id"), nullable=False)
    destination_account_id = Column(BigInteger, ForeignKey("account.id"), nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    payment_method = Column(String(10), nullable=False)
    status = Column(String(10), nullable=False)
    reverses_transaction_id = Column(BigInteger, ForeignKey("transaction.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("transaction_key", name="uq_transaction_key"),
        # Uma compra são várias linhas com a MESMA chave (leg 1, 2, 3):
        # o que é único é o par, nunca a chave ou a leg sozinhas.
        UniqueConstraint("idempotency_key", "leg", name="uq_transaction_idempotency_leg"),
        UniqueConstraint("reverses_transaction_id", name="uq_transaction_reversal"),
    )

    source_account = relationship("Account", foreign_keys=[source_account_id], lazy="joined")
    destination_account = relationship("Account", foreign_keys=[destination_account_id], lazy="joined")
    reversed_transaction = relationship("Transaction", remote_side=[id], foreign_keys=[reverses_transaction_id])

    BALANCE_METHOD = "balance"
    CARD_METHOD = "card"
    PIX_METHOD = "pix"
    CASH_METHOD = "cash"

    PENDING_STATUS = "pending"
    SETTLED_STATUS = "settled"
    REVERSED_STATUS = "reversed"
    CANCELED_STATUS = "canceled"

    STATUSES_THAT_MOVED_MONEY = (SETTLED_STATUS, REVERSED_STATUS)
