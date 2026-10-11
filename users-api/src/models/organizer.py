from sqlalchemy import BigInteger, Column, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class Organizer(Base):
    __tablename__ = "organizer"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organizer_key = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    document = Column(String(18), nullable=False)
    password_hash = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("organizer_key", name="uq_organizer_key"),
        UniqueConstraint("email", name="uq_organizer_email"),
        UniqueConstraint("document", name="uq_organizer_document"),
    )

    USER_TYPE = "organizer"
