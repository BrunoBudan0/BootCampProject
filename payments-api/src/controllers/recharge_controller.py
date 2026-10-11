import hashlib
import hmac
import json
from datetime import datetime

import requests
from jsonschema import ValidationError, validate
from sqlalchemy.exc import IntegrityError

from connectors import CardProviderConnector, PixProviderConnector
from constants import PIX_WEBHOOK_SECRET
from controllers.account_controller import parse_uuid_or_none
from controllers.money_moving_controller import MoneyMovingController
from dtos import TransactionDTO
from errors import (
    BlockedAccount,
    CardDeclined,
    EventWithoutExternalAccount,
    IdempotencyKeyConflict,
    InvalidPixSignature,
    InvalidSchema,
    InvalidStatusTransition,
    NotFoundTransaction,
    PixAmountMismatch,
    ProviderUnavailable,
)
from models import Account, CriticalLogPayment, Transaction
from repositories import PixChargeRepository
from utils.schema_handler import SchemaCache, describe_schema_error

CARD_APPROVED = "approved"
CARD_DECLINED = "declined"
PIX_PAID = "paid"
PIX_EXPIRED = "expired"
PIX_WEBHOOK_SCHEMA = "put_pix_webhook.json"
PIX_CHARGE_FIELDS = ("charge_id", "copy_paste", "expires_at")


class RechargeController(MoneyMovingController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.pix_charge_repository = PixChargeRepository(self.context)

    def recharge_for_caller(self, payload: dict) -> tuple:
        account = self.account_controller.find_account_owned_by_caller(payload["account_id"])
        idempotency_key = payload["idempotency_key"]

        recorded_transactions = self.transaction_repository.list_transactions_by_idempotency_key(idempotency_key)
        if recorded_transactions:
            return self._replay_recharge(recorded_transactions, account, payload), False

        self.refuse_non_positive_amounts([payload["amount_cents"]])
        if account.blocked:
            raise BlockedAccount(account.account_key)

        external_account = self.account_repository.get_system_account_of_event(account.event_id, Account.EXTERNAL_KIND)
        if external_account is None:
            raise EventWithoutExternalAccount(account.event_id)

        try:
            pending_recharge = self._record_pending_recharge(account, external_account, payload)
        except IntegrityError as integrity_error:
            recorded_transactions = self.transactions_already_recorded_after_race(integrity_error, idempotency_key)
            return self._replay_recharge(recorded_transactions, account, payload), False

        if payload["payment_method"] == Transaction.CARD_METHOD:
            return self._recharge_by_card(pending_recharge, payload), True

        return self._recharge_by_pix(pending_recharge, payload), True

    def handle_pix_webhook(self, transaction_id: str, raw_body: bytes, signature) -> None:
        if not pix_signature_matches(raw_body, signature):
            self._refuse_pix_notice(transaction_id, "the signature does not match the body")

        notice = parse_pix_notice(raw_body)
        if not notice_belongs_to(notice, transaction_id):
            self._refuse_pix_notice(transaction_id, "the signed notice belongs to another charge")

        transaction = self._find_pix_transaction(transaction_id)

        if notice["status"] == PIX_PAID:
            self._settle_pix(transaction, notice["amount_cents"])
        else:
            self._cancel_expired_pix(transaction)

    def _record_pending_recharge(self, account, external_account, payload: dict):
        pending_recharge = self.transaction_repository.create_transaction(
            idempotency_key=payload["idempotency_key"],
            leg=1,
            source_account=external_account,
            destination_account=account,
            amount_cents=payload["amount_cents"],
            payment_method=payload["payment_method"],
            status=Transaction.PENDING_STATUS,
        )
        self.session.commit()

        return pending_recharge

    def _recharge_by_card(self, pending_recharge, payload: dict) -> dict:
        idempotency_key = payload["idempotency_key"]
        amount_cents = payload["amount_cents"]

        try:
            provider_response = CardProviderConnector().authorize(
                card_token=payload["card_token"], amount_cents=amount_cents, reference=idempotency_key
            )
        except requests.exceptions.ReadTimeout:
            self.critical_log_repository.record(
                CriticalLogPayment.CARD_OUTCOME_UNKNOWN,
                route="/recharges",
                error_code=ProviderUnavailable.code,
                user_id=self.context.caller_id,
                transaction=pending_recharge,
                idempotency_key=idempotency_key,
                amount_cents=amount_cents,
            )
            raise ProviderUnavailable("card")
        except requests.exceptions.RequestException:
            self._cancel_pending_recharge(pending_recharge)
            raise ProviderUnavailable("card")

        card_status = provider_response.json.get("status") if isinstance(provider_response.json, dict) else None
        if provider_response.status >= 500 or card_status not in (CARD_APPROVED, CARD_DECLINED):
            self._cancel_pending_recharge(pending_recharge)
            raise ProviderUnavailable("card")

        if card_status == CARD_DECLINED:
            self._cancel_pending_recharge(pending_recharge)
            raise CardDeclined()

        try:
            self._settle_pending_recharge(pending_recharge)
            recharge_dto = TransactionDTO.obj_to_dict(pending_recharge)
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.critical_log_repository.record(
                CriticalLogPayment.CARD_AUTHORIZED_NOT_CREDITED,
                route="/recharges",
                user_id=self.context.caller_id,
                transaction=pending_recharge,
                idempotency_key=idempotency_key,
                amount_cents=amount_cents,
            )
            raise

        self.logger.info(f"Card recharge {recharge_dto['id']} of {amount_cents} cents")
        return recharge_dto

    def _recharge_by_pix(self, pending_recharge, payload: dict) -> dict:
        amount_cents = payload["amount_cents"]

        try:
            provider_response = PixProviderConnector().create_charge(
                amount_cents=amount_cents, reference=str(pending_recharge.transaction_key)
            )
        except requests.exceptions.RequestException:
            self._cancel_pending_recharge(pending_recharge)
            raise ProviderUnavailable("pix")

        charge = provider_response.json if isinstance(provider_response.json, dict) else {}
        charge_is_complete = all(field in charge for field in PIX_CHARGE_FIELDS)
        charge_expires_at = parse_provider_datetime(charge.get("expires_at"))
        if provider_response.status >= 300 or not charge_is_complete or charge_expires_at is None:
            self._cancel_pending_recharge(pending_recharge)
            raise ProviderUnavailable("pix")

        pix_charge = self.pix_charge_repository.create_pix_charge(
            pending_recharge, charge["charge_id"], charge["copy_paste"], charge_expires_at
        )
        recharge_dto = TransactionDTO.with_pix_charge(pending_recharge, pix_charge)
        self.session.commit()
        self.logger.info(f"Pix charge {recharge_dto['id']} of {amount_cents} cents waiting for payment")
        return recharge_dto

    def _settle_pending_recharge(self, pending_recharge) -> bool:
        self.account_repository.lock_accounts_in_id_order(
            [pending_recharge.source_account_id, pending_recharge.destination_account_id]
        )
        recharge = self.transaction_repository.reload_transaction(pending_recharge)

        settled_now = self.transaction_repository.change_status_if_current(
            recharge, Transaction.PENDING_STATUS, Transaction.SETTLED_STATUS
        )
        if settled_now:
            self.debit_or_refuse(recharge.source_account, recharge.amount_cents)
            self.account_repository.credit(recharge.destination_account, recharge.amount_cents)

        return settled_now

    def _cancel_pending_recharge(self, pending_recharge) -> None:
        self.transaction_repository.change_status_if_current(
            pending_recharge, Transaction.PENDING_STATUS, Transaction.CANCELED_STATUS
        )
        self.session.commit()
        self.logger.info(f"Recharge {pending_recharge.transaction_key} canceled")

    def _replay_recharge(self, recorded_transactions, account, payload: dict) -> dict:
        recorded = recorded_transactions[0]
        same_request = (
            len(recorded_transactions) == 1
            and recorded.destination_account_id == account.id
            and recorded.payment_method == payload["payment_method"]
            and recorded.amount_cents == payload["amount_cents"]
        )
        if not same_request:
            raise IdempotencyKeyConflict(payload["idempotency_key"])

        self.logger.info(f"Replaying recharge {recorded.transaction_key}")
        if recorded.payment_method == Transaction.PIX_METHOD:
            pix_charge = self.pix_charge_repository.get_pix_charge_of_transaction(recorded)
            return TransactionDTO.with_pix_charge(recorded, pix_charge)

        return TransactionDTO.obj_to_dict(recorded)

    def _refuse_pix_notice(self, transaction_id: str, reason: str) -> None:
        invalid_signature = InvalidPixSignature()
        self.critical_log_repository.record(
            CriticalLogPayment.PIX_INVALID_SIGNATURE,
            route=f"/webhooks/pix/{transaction_id}",
            http_status=invalid_signature.http_status,
            error_code=invalid_signature.code,
            description=reason,
        )
        raise invalid_signature

    def _find_pix_transaction(self, transaction_id: str):
        transaction_key = parse_uuid_or_none(transaction_id)
        transaction = None
        if transaction_key is not None:
            transaction = self.transaction_repository.get_transaction_by_key(transaction_key)

        if transaction is None or transaction.payment_method != Transaction.PIX_METHOD:
            raise NotFoundTransaction(transaction_id)

        return transaction

    def _settle_pix(self, transaction, paid_amount_cents: int) -> None:
        if paid_amount_cents != transaction.amount_cents:
            self.critical_log_repository.record(
                CriticalLogPayment.PIX_AMOUNT_MISMATCH,
                route=f"/webhooks/pix/{transaction.transaction_key}",
                error_code=PixAmountMismatch.code,
                transaction=transaction,
                amount_cents=paid_amount_cents,
            )
            raise PixAmountMismatch(transaction.amount_cents, paid_amount_cents)

        settled_now = self._settle_pending_recharge(transaction)
        if settled_now:
            self.session.commit()
            self.logger.info(f"Pix {transaction.transaction_key} paid and credited")
            return

        if transaction.status != Transaction.SETTLED_STATUS:
            raise InvalidStatusTransition(transaction.status, Transaction.SETTLED_STATUS)

        self.logger.info(f"Pix {transaction.transaction_key} was already paid: nothing credited again")

    def _cancel_expired_pix(self, transaction) -> None:
        canceled_now = self.transaction_repository.change_status_if_current(
            transaction, Transaction.PENDING_STATUS, Transaction.CANCELED_STATUS
        )
        if canceled_now:
            self.session.commit()
            self.logger.info(f"Pix {transaction.transaction_key} expired and was canceled")
            return

        if transaction.status != Transaction.CANCELED_STATUS:
            raise InvalidStatusTransition(transaction.status, Transaction.CANCELED_STATUS)


def pix_signature_matches(raw_body: bytes, signature) -> bool:
    if not signature:
        return False

    expected_signature = hmac.new(PIX_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_signature.encode("utf-8"), signature.encode("utf-8"))


def parse_pix_notice(raw_body: bytes) -> dict:
    try:
        notice = json.loads(raw_body)
    except ValueError:
        raise InvalidSchema("the webhook body is not valid JSON")

    try:
        validate(notice, SchemaCache.get_schema(PIX_WEBHOOK_SCHEMA))
    except ValidationError as error:
        raise InvalidSchema(describe_schema_error(error))

    return notice


def notice_belongs_to(notice: dict, transaction_id: str) -> bool:
    notice_reference = parse_uuid_or_none(notice["reference"])
    return notice_reference is not None and notice_reference == parse_uuid_or_none(transaction_id)


def parse_provider_datetime(raw_value):
    try:
        return datetime.fromisoformat(raw_value)
    except (TypeError, ValueError):
        return None
