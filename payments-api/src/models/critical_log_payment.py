from sqlalchemy import CHAR, BigInteger, Column, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class CriticalLogPayment(Base):
    """Uma linha por acontecimento crítico. Só INSERT: o banco recusa o resto.

    Os campos obrigatórios de cada `type` são cobrados pelo CHECK
    ck_critical_log_payment_fields do database.sql — este model não repete
    a regra, só descreve a tabela.
    """

    __tablename__ = "critical_log_payment"

    id = Column(BigInteger, primary_key=True)
    request_id = Column(String(64))
    type = Column(String(40), nullable=False)
    route = Column(String(120))
    http_status = Column(SmallInteger)
    error_code = Column(CHAR(9))
    user_id = Column(UUID(as_uuid=True))  # REF: API de Usuários
    account_id = Column(BigInteger, ForeignKey("account.id"))
    transaction_id = Column(BigInteger, ForeignKey("transaction.id"))
    idempotency_key = Column(String(80))
    amount_cents = Column(BigInteger)
    description = Column(String(500))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    INTERNAL_CALL_REJECTED = "INTERNAL_CALL_REJECTED"
    BALANCE_CHECK_TRIGGERED = "BALANCE_CHECK_TRIGGERED"
    CARD_AUTHORIZED_NOT_CREDITED = "CARD_AUTHORIZED_NOT_CREDITED"
    CARD_OUTCOME_UNKNOWN = "CARD_OUTCOME_UNKNOWN"
    PIX_INVALID_SIGNATURE = "PIX_INVALID_SIGNATURE"
    PIX_AMOUNT_MISMATCH = "PIX_AMOUNT_MISMATCH"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
