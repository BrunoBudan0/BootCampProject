from database import SessionLocal
from models import CriticalLogPayment
from utils.logger import get_logger
from utils.request_context import NO_REQUEST_ID, get_request_id


class CriticalLogRepository:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    def record(
        self,
        log_type,
        route=None,
        http_status=None,
        error_code=None,
        user_id=None,
        account=None,
        transaction=None,
        idempotency_key=None,
        amount_cents=None,
        description=None,
    ):
        request_id = get_request_id()
        self.logger.critical(f"{log_type} route={route} http_status={http_status} error_code={error_code}")

        own_session = SessionLocal()
        try:
            own_session.add(
                CriticalLogPayment(
                    request_id=None if request_id == NO_REQUEST_ID else request_id,
                    type=log_type,
                    route=route,
                    http_status=http_status,
                    error_code=error_code,
                    user_id=user_id,
                    account_id=account.id if account is not None else None,
                    transaction_id=transaction.id if transaction is not None else None,
                    idempotency_key=idempotency_key,
                    amount_cents=amount_cents,
                    description=description,
                )
            )
            own_session.commit()
        except Exception:
            own_session.rollback()
            self.logger.critical(f"CRITICAL_LOG_LOST {log_type} request_id={request_id}")
        finally:
            own_session.close()
