from sqlalchemy import BigInteger, Column, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class Company(Base):
    __tablename__ = "company"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_key = Column(UUID(as_uuid=True), nullable=False)
    legal_name = Column(String(255), nullable=False)
    trade_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    document = Column(String(18), nullable=False)
    password_hash = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("company_key", name="uq_company_key"),
        UniqueConstraint("email", name="uq_company_email"),
        UniqueConstraint("document", name="uq_company_document"),
    )

    USER_TYPE = "company"
