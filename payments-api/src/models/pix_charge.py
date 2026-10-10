from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text, UniqueConstraint, func

from models.base import Base


class PixCharge(Base):

    __tablename__ = "pix_charge"

    id = Column(BigInteger, primary_key=True)
    transaction_id = Column(BigInteger, ForeignKey("transaction.id"), nullable=False)
    provider_charge_id = Column(String(80), nullable=False)
    copy_paste = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("transaction_id", name="uq_pix_charge_transaction"),)
