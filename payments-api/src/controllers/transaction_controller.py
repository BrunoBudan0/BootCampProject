from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from controllers.account_controller import parse_uuid_or_none
from controllers.money_moving_controller import IDEMPOTENCY_CONSTRAINT, MoneyMovingController
from dtos import TransactionDTO
from errors import (
    AlreadyReversed,
    DestinationRefusesTransfers,
    IdempotencyKeyConflict,
    InvalidParameter,
    InvalidSchema,
    NotFoundTransaction,
    SourceIsNotAnAttendee,
)
from models import Account, Transaction
from utils.integrity_error import violated_constraint_name

REVERSAL_CONSTRAINT = "uq_transaction_reversal"
REVERSAL_RACE_CONSTRAINTS = (IDEMPOTENCY_CONSTRAINT, REVERSAL_CONSTRAINT)
SAO_PAULO_TIMEZONE = ZoneInfo("America/Sao_Paulo")
DATE_AND_TIME_SEPARATOR = "T"
SMALLEST_STORED_TIME_STEP = timedelta(microseconds=1)


class TransactionController(MoneyMovingController):
    def __init__(self) -> None:
        super().__init__(__name__)

    def execute_internal_transactions(self, payload: dict) -> tuple:
        idempotency_key = payload["idempotency_key"]
        payment_method = payload["payment_method"]
        requested_transfers = payload["transfers"]

        recorded_transactions = self.transaction_repository.list_transactions_by_idempotency_key(idempotency_key)
        if recorded_transactions:
            return self._replay_batch(recorded_transactions, payload), False

        self.refuse_non_positive_amounts([transfer["amount_cents"] for transfer in requested_transfers])
        resolved_transfers = [
            (
                self.account_controller.find_account_or_fail(transfer["source_account_id"]),
                self.account_controller.find_account_or_fail(transfer["destination_account_id"]),
                transfer["amount_cents"],
            )
            for transfer in requested_transfers
        ]
        self.refuse_invalid_transfers(resolved_transfers)

        try:
            created_transactions = self.move_money(idempotency_key, payment_method, resolved_transfers)
        except IntegrityError as integrity_error:
            recorded_transactions = self.transactions_already_recorded_after_race(integrity_error, idempotency_key)
            return self._replay_batch(recorded_transactions, payload), False

        batch_dto = TransactionDTO.batch_to_dict(idempotency_key, created_transactions)
        self.session.commit()
        self.logger.info(f"Moved money under key {idempotency_key}: {len(created_transactions)} transactions")
        return batch_dto, True

    def transfer_for_caller(self, payload: dict) -> tuple:
        source_account = self.account_controller.find_account_owned_by_caller(payload["source_account_id"])
        if source_account.holder_type != Account.ATTENDEE_HOLDER:
            raise SourceIsNotAnAttendee()

        idempotency_key = payload["idempotency_key"]

        recorded_transactions = self.transaction_repository.list_transactions_by_idempotency_key(idempotency_key)
        if recorded_transactions:
            return self._replay_transfer(recorded_transactions, source_account, payload), False

        amount_cents = payload["amount_cents"]
        self.refuse_non_positive_amounts([amount_cents])
        destination_account = self.account_controller.find_account_or_fail(payload["destination_account_id"])
        resolved_transfers = [(source_account, destination_account, amount_cents)]
        self.refuse_invalid_transfers(resolved_transfers)
        if destination_account.holder_type != Account.ATTENDEE_HOLDER or destination_account.blocked:
            raise DestinationRefusesTransfers()

        try:
            created_transactions = self.move_money(idempotency_key, Transaction.BALANCE_METHOD, resolved_transfers)
        except IntegrityError as integrity_error:
            recorded_transactions = self.transactions_already_recorded_after_race(integrity_error, idempotency_key)
            return self._replay_transfer(recorded_transactions, source_account, payload), False

        transfer_dto = TransactionDTO.obj_to_dict(created_transactions[0])
        self.session.commit()
        self.logger.info(f"Transfer {transfer_dto['id']} of {amount_cents} cents")
        return transfer_dto, True

    def reverse_transactions(self, payload: dict) -> tuple:
        original_idempotency_key = payload["original_idempotency_key"]
        reversal_idempotency_key = payload["idempotency_key"]

        original_transactions = self.transaction_repository.list_transactions_by_idempotency_key(original_idempotency_key)
        if not original_transactions:
            raise NotFoundTransaction(original_idempotency_key)

        recorded_reversals = self.transaction_repository.list_transactions_by_idempotency_key(reversal_idempotency_key)
        if recorded_reversals:
            return self._replay_reversal(recorded_reversals, original_idempotency_key), False

        if any(original.status != Transaction.SETTLED_STATUS for original in original_transactions):
            raise AlreadyReversed(original_idempotency_key)

        reversal_order = sorted(
            original_transactions,
            key=lambda original: (original.destination_account.kind == Account.USER_KIND, original.leg),
        )

        try:
            created_reversals = self._create_reversals(reversal_order, reversal_idempotency_key, original_idempotency_key)
        except IntegrityError as integrity_error:
            if violated_constraint_name(integrity_error) not in REVERSAL_RACE_CONSTRAINTS:
                raise
            self.session.rollback()
            recorded_reversals = self.transaction_repository.list_transactions_by_idempotency_key(reversal_idempotency_key)
            if not recorded_reversals:
                raise AlreadyReversed(original_idempotency_key)
            return self._replay_reversal(recorded_reversals, original_idempotency_key), False

        batch_dto = TransactionDTO.batch_to_dict(reversal_idempotency_key, created_reversals)
        self.session.commit()
        self.logger.info(f"Reversed key {original_idempotency_key} under key {reversal_idempotency_key}")
        return batch_dto, True

    def get_transaction_for_caller(self, transaction_id: str) -> dict:
        transaction_key = parse_uuid_or_none(transaction_id)
        transaction = None
        if transaction_key is not None:
            transaction = self.transaction_repository.get_transaction_by_key(transaction_key)

        caller_id = self.context.caller_id
        caller_is_involved = (
            transaction is not None
            and caller_id is not None
            and caller_id in (transaction.source_account.holder_id, transaction.destination_account.holder_id)
        )
        if not caller_is_involved:
            raise NotFoundTransaction(transaction_id)

        return TransactionDTO.obj_to_dict(transaction)

    def statement_for_caller(self, account_id: str, limit: int, page: int, raw_date_from, raw_date_to) -> dict:
        account = self.account_controller.find_account_owned_by_caller(account_id)
        settled_from = start_of_period(raw_date_from)
        settled_before = end_of_period_exclusive(raw_date_to)
        if settled_from is not None and settled_before is not None and settled_from >= settled_before:
            raise InvalidSchema("date_from must not be after date_to")

        statement_lines = self.transaction_repository.statement_page(
            account, settled_from, settled_before, limit=limit + 1, offset=(page - 1) * limit
        )
        is_last_page = len(statement_lines) <= limit

        return TransactionDTO.statement_to_dict(statement_lines[:limit], limit, page, is_last_page)

    def _create_reversals(self, reversal_order, reversal_idempotency_key, original_idempotency_key):
        resolved_reversals = [
            (original.destination_account, original.source_account, original.amount_cents) for original in reversal_order
        ]
        self.lock_accounts_of(resolved_reversals)

        created_reversals = []
        for leg, original in enumerate(reversal_order, start=1):
            created_reversals.append(
                self.transaction_repository.create_transaction(
                    idempotency_key=reversal_idempotency_key,
                    leg=leg,
                    source_account=original.destination_account,
                    destination_account=original.source_account,
                    amount_cents=original.amount_cents,
                    payment_method=original.payment_method,
                    status=Transaction.SETTLED_STATUS,
                    reversed_transaction=original,
                )
            )

        for original in reversal_order:
            original_was_settled = self.transaction_repository.change_status_if_current(
                original, Transaction.SETTLED_STATUS, Transaction.REVERSED_STATUS
            )
            if not original_was_settled:
                self.session.rollback()
                raise AlreadyReversed(original_idempotency_key)

        for source_account, destination_account, amount_cents in resolved_reversals:
            self.debit_or_refuse(source_account, amount_cents)
            self.account_repository.credit(destination_account, amount_cents)

        return created_reversals

    def _replay_batch(self, recorded_transactions, payload: dict) -> dict:
        requested_transfers = payload["transfers"]
        same_request = len(recorded_transactions) == len(requested_transfers) and all(
            recorded.payment_method == payload["payment_method"]
            and recorded.source_account.account_key == parse_uuid_or_none(requested["source_account_id"])
            and recorded.destination_account.account_key == parse_uuid_or_none(requested["destination_account_id"])
            and recorded.amount_cents == requested["amount_cents"]
            for recorded, requested in zip(recorded_transactions, requested_transfers)
        )
        if not same_request:
            raise IdempotencyKeyConflict(payload["idempotency_key"])

        self.logger.info(f"Replaying transactions of key {payload['idempotency_key']}")
        return TransactionDTO.batch_to_dict(payload["idempotency_key"], recorded_transactions)

    def _replay_transfer(self, recorded_transactions, source_account, payload: dict) -> dict:
        recorded = recorded_transactions[0]
        same_request = (
            len(recorded_transactions) == 1
            and recorded.payment_method == Transaction.BALANCE_METHOD
            and recorded.source_account_id == source_account.id
            and recorded.destination_account.account_key == parse_uuid_or_none(payload["destination_account_id"])
            and recorded.amount_cents == payload["amount_cents"]
        )
        if not same_request:
            raise IdempotencyKeyConflict(payload["idempotency_key"])

        self.logger.info(f"Replaying transfer {recorded.transaction_key}")
        return TransactionDTO.obj_to_dict(recorded)

    def _replay_reversal(self, recorded_reversals, original_idempotency_key) -> dict:
        reverses_the_same_originals = all(
            reversal.reversed_transaction is not None
            and reversal.reversed_transaction.idempotency_key == original_idempotency_key
            for reversal in recorded_reversals
        )
        if not reverses_the_same_originals:
            raise IdempotencyKeyConflict(recorded_reversals[0].idempotency_key)

        self.logger.info(f"Replaying reversal of key {original_idempotency_key}")
        return TransactionDTO.batch_to_dict(recorded_reversals[0].idempotency_key, recorded_reversals)


def start_of_period(raw_date_from):
    if raw_date_from is None:
        return None

    if DATE_AND_TIME_SEPARATOR not in raw_date_from:
        return midnight_in_sao_paulo(parse_query_date(raw_date_from, "date_from"))

    return parse_query_moment(raw_date_from, "date_from")


def end_of_period_exclusive(raw_date_to):
    if raw_date_to is None:
        return None

    if DATE_AND_TIME_SEPARATOR not in raw_date_to:
        return midnight_in_sao_paulo(parse_query_date(raw_date_to, "date_to") + timedelta(days=1))

    return parse_query_moment(raw_date_to, "date_to") + SMALLEST_STORED_TIME_STEP


def midnight_in_sao_paulo(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=SAO_PAULO_TIMEZONE)


def parse_query_date(raw_value, parameter_name) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        raise InvalidParameter(f"{parameter_name} is not a valid date")


def parse_query_moment(raw_value, parameter_name) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        raise InvalidParameter(f"{parameter_name} is not a valid date")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=SAO_PAULO_TIMEZONE)

    return parsed
