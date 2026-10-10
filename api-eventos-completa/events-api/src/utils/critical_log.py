import uuid

from database import SessionLocal
from models import CriticalLogEvent, CriticalLogType
from utils.logger import get_logger
from utils.request_context import NO_REQUEST_ID, get_request_id

logger = get_logger(__name__)


def critical_log(log_type: CriticalLogType, description: str, **fields) -> None:
    # sessão própria: o log fica gravado mesmo se a requisição for desfeita
    request_id = get_request_id()
    session = SessionLocal()
    try:
        session.add(CriticalLogEvent(
            id=uuid.uuid4(),
            type=log_type.value,
            request_id=None if request_id == NO_REQUEST_ID else request_id,
            description=description[:500],
            **fields,
        ))
        session.commit()
    except Exception:
        session.rollback()
        logger.exception(f"não consegui gravar o log crítico {log_type.value}")
    finally:
        session.close()

    logger.warning(f"[{log_type.value}] {description}")


def parse_user_id(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        return None
