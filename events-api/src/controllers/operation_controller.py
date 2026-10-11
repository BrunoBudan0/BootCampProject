import uuid
from datetime import datetime, timezone

from connectors import PaymentsConnector
from controllers.base_controller import BaseController
from dtos import credential_to_dict
from errors import (
    CredentialBlocked,
    CredentialNotFound,
    EventClosed,
    EventNotFound,
    IdempotencyKeyReused,
    NonPositiveAmount,
    NotAllowedForUserType,
    UpstreamUnavailable,
)
from models import CriticalLogType, Event, TransactionType, UserType
from repositories import EventAttendeeRepository, EventRepository, PurchaseRepository
from utils.critical_log import critical_log


class OperationController(BaseController):
    """O que o organizador faz durante a feira: bloqueio, recarga em espécie e fechamento."""

    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.events = EventRepository(self.session)
        self.credentials = EventAttendeeRepository(self.session)
        self.purchases = PurchaseRepository(self.session)
        self.payments = PaymentsConnector()

    def set_blocked(self, user_id: uuid.UUID, user_type: str, credential_id: uuid.UUID, blocked: bool) -> dict:
        credential = self.credentials.get_by_id(credential_id)
        event = self.events.get_by_id(credential.event_id) if credential else None
        if credential is None or event is None or not self._is_organizer(user_id, user_type, event):
            raise CredentialNotFound()

        account_id = credential.account_id
        self.session.rollback()

        # a conta primeiro: se Pagamentos falhar, nada muda aqui e o pedido pode ser repetido
        self.payments.set_blocked(account_id, blocked)

        changed = self.credentials.set_blocked(credential, blocked)
        self.session.commit()

        if changed:
            critical_log(
                CriticalLogType.CREDENTIAL_BLOCK_CHANGED,
                f"credencial {'bloqueada' if blocked else 'liberada'} pelo organizador",
                event_id=event.id,
                event_attendee_id=credential.id,
                user_id=user_id,
                account_id=account_id,
            )
        return credential_to_dict(credential)

    def cash_recharge(self, user_id: uuid.UUID, user_type: str, event_id: uuid.UUID, payload: dict) -> tuple[dict, bool]:
        if user_type != UserType.ORGANIZER.value:
            raise NotAllowedForUserType()

        event = self._owned_event(user_id, user_type, event_id)
        if not event.active:
            raise EventClosed()

        credential = self.credentials.get_by_id(uuid.UUID(payload["event_attendee_id"]))
        if credential is None or credential.event_id != event.id:
            raise CredentialNotFound()
        if credential.blocked:
            raise CredentialBlocked()

        amount = payload["amount_cents"]
        if amount <= 0:
            raise NonPositiveAmount()

        # a chave do app vale só dentro deste evento
        key = f"cash:{uuid.uuid5(event.id, payload['idempotency_key'])}"
        legs = [(TransactionType.DEPOSIT.value, event.external_account_id, credential.account_id, amount)]
        credential_id = credential.id

        self.session.rollback()
        result = self.payments.transfer(key, "cash", legs)

        if result.outcome == "done":
            self.logger.info(f"recarga em espécie de {amount} na credencial {credential_id} por {user_id}")
            transaction = result.transactions[0] if result.transactions else {}
            body = {
                "event_id": str(event_id),
                "event_attendee_id": str(credential_id),
                "amount_cents": amount,
                "payment_method": "cash",
                "idempotency_key": payload["idempotency_key"],
                "transaction_id": transaction.get("id"),
                "launched_by": str(user_id),
            }
            return body, result.status == 201

        if result.outcome == "refused":
            if result.code == "QIT002022":
                raise CredentialBlocked()
            if result.code == "QIT002025":
                raise IdempotencyKeyReused()
            if result.code == "QIT002028":
                raise NonPositiveAmount()
            self.logger.error(f"recusa inesperada de Pagamentos na recarga {key}: {result.code}")
            raise UpstreamUnavailable()

        # pode ter entrado: o organizador repete com a mesma chave e não duplica
        raise UpstreamUnavailable()

    def reconciliation(self, user_id: uuid.UUID, user_type: str, event_id: uuid.UUID) -> dict:
        event = self._owned_event(user_id, user_type, event_id)
        purchases = self.purchases.summary_of_event(event.id)
        fee_net = self.purchases.fee_net_of_event(event.id)

        self.session.rollback()
        report = self.payments.reconciliation(event_id)

        sum_cents = int(report.get("sum_cents", 0))
        mismatches = report.get("mismatches", [])
        ok = sum_cents == 0 and not mismatches

        if not ok:
            critical_log(
                CriticalLogType.RECONCILIATION_MISMATCH,
                f"soma {sum_cents} e {len(mismatches)} conta(s) divergente(s)",
                event_id=event_id,
                amount_cents=sum_cents,
                user_id=user_id,
            )

        return {
            "event_id": str(event_id),
            "ok": ok,
            "sum_cents": sum_cents,
            "mismatches": mismatches,
            "purchases": purchases,
            "fee_net_cents": fee_net,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def fee_charges(self, user_id: uuid.UUID, user_type: str, event_id: uuid.UUID, limit: int, page: int) -> dict:
        event = self._owned_event(user_id, user_type, event_id)
        rows, is_last_page = self.purchases.fee_charges_of_event(event.id, limit, page)
        return {
            "data": [
                {
                    "id": str(charge.id),
                    "purchase_id": str(charge.purchase_id),
                    "kind": charge.kind,
                    "base_cents": charge.base_cents,
                    "amount_cents": charge.amount_cents,
                    "fee_rate_id": str(charge.fee_rate_id),
                    "rate_bps": rate_bps,
                    "transaction_id": str(charge.transaction_id) if charge.transaction_id else None,
                    "created_at": charge.created_at.isoformat(),
                }
                for charge, rate_bps in rows
            ],
            "net_cents": self.purchases.fee_net_of_event(event.id),
            "is_last_page": is_last_page,
        }

    def _owned_event(self, user_id, user_type, event_id) -> Event:
        event = self.events.get_by_id(event_id)
        if event is None or not self._is_organizer(user_id, user_type, event):
            raise EventNotFound()
        return event

    @staticmethod
    def _is_organizer(user_id, user_type, event: Event) -> bool:
        return user_type == UserType.ORGANIZER.value and event.organizer_id == user_id
