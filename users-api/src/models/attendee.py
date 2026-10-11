from sqlalchemy import CHAR, BigInteger, Column, Date, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class Attendee(Base):
    __tablename__ = "attendee"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    attendee_key = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    document = Column(String(14), nullable=False)
    password_hash = Column(String(255), nullable=False)
    birth_date = Column(Date, nullable=False)
    phone = Column(String(20), nullable=True)
    postal_code = Column(CHAR(9), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("attendee_key", name="uq_attendee_key"),
        UniqueConstraint("email", name="uq_attendee_email"),
        UniqueConstraint("document", name="uq_attendee_document"),
    )

    USER_TYPE = "attendee"
