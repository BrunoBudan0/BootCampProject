from enum import Enum


# mesmos valores dos CHECKs do database.sql


class PurchaseStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class FeeChargeKind(str, Enum):
    CHARGE = "charge"
    REFUND = "refund"


class UserType(str, Enum):
    ATTENDEE = "attendee"
    ORGANIZER = "organizer"
    COMPANY = "company"


# donos: API de Pagamentos (usados no POST /internal/transactions)
class PaymentMethod(str, Enum):
    BALANCE = "balance"
    CARD = "card"
    PIX = "pix"
    CASH = "cash"


class CriticalLogType(str, Enum):
    INTERNAL_CALL_REJECTED = "INTERNAL_CALL_REJECTED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
    ORPHAN_ACCOUNT = "ORPHAN_ACCOUNT"
    CREDENTIAL_BLOCK_CHANGED = "CREDENTIAL_BLOCK_CHANGED"
    STOCK_CHECK_TRIGGERED = "STOCK_CHECK_TRIGGERED"
    PURCHASE_OUTCOME_UNKNOWN = "PURCHASE_OUTCOME_UNKNOWN"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
