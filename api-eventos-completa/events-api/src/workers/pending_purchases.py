import threading
from datetime import datetime, timedelta, timezone

from constants import PENDING_ALERT_SECONDS, PENDING_RETRY_SECONDS
from controllers import PurchaseController
from database import clear_context, get_context, open_context
from errors import QIException
from models import CriticalLogType, PurchaseStatus
from utils.critical_log import critical_log
from utils.logger import get_logger

logger = get_logger(__name__)

BATCH_SIZE = 20


def settle_pending_once(older_than_seconds: int = PENDING_RETRY_SECONDS) -> int:
    # fora de uma requisição não existe middleware abrindo o contexto: abre aqui
    open_context()
    try:
        controller = PurchaseController()
        ids = controller.purchases.pending_ids(older_than_seconds, BATCH_SIZE)
        for purchase_id in ids:
            try:
                controller.settle(purchase_id)
            except QIException:
                pass
            _alert_if_stuck(controller, purchase_id)
        return len(ids)
    finally:
        session = get_context().db_session
        if session is not None:
            session.rollback()
            session.close()
        clear_context()


def _alert_if_stuck(controller: PurchaseController, purchase_id) -> None:
    purchase = controller.purchases.get_by_id(purchase_id)
    if purchase is None or purchase.status != PurchaseStatus.PENDING.value:
        return

    age = datetime.now(timezone.utc).replace(tzinfo=None) - purchase.created_at
    if age < timedelta(seconds=PENDING_ALERT_SECONDS):
        return
    if controller.purchases.has_critical_log(CriticalLogType.PURCHASE_OUTCOME_UNKNOWN.value, purchase_id):
        return

    controller.session.rollback()
    critical_log(
        CriticalLogType.PURCHASE_OUTCOME_UNKNOWN,
        f"compra pending há {int(age.total_seconds())}s sem resposta de Pagamentos",
        purchase_id=purchase_id,
    )


def _loop(stop: threading.Event) -> None:
    logger.info(f"rotina de compras pendentes a cada {PENDING_RETRY_SECONDS}s")
    while not stop.wait(PENDING_RETRY_SECONDS):
        try:
            resolved = settle_pending_once()
            if resolved:
                logger.info(f"rotina revisou {resolved} compra(s) pendente(s)")
        except Exception:
            logger.exception("a rotina de compras pendentes falhou; tenta de novo na próxima volta")


def start_pending_worker() -> threading.Event | None:
    if PENDING_RETRY_SECONDS <= 0:
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(stop,), name="pending-purchases", daemon=True).start()
    return stop
