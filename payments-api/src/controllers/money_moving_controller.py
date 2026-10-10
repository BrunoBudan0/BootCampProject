from sqlalchemy.exc import IntegrityError

from controllers.account_controller import AccountController
from controllers.base_controller import BaseController
from errors import (
    BlockedAccount,
    DifferentEvents,
    InsufficientBalance,
    InvalidAmount,
    SameAccount,
)
from models import CriticalLogPayment, Transaction
from repositories import AccountRepository, CriticalLogRepository, TransactionRepository

BALANCE_CHECK_CONSTRAINT = "ck_account_user_balance"


class MoneyMovingController(BaseController):
    def __init__(self, class_name: str) -> None:
        super().__init__(class_name)
        self.account_repository = AccountRepository(self.context)
        self.transaction_repository = TransactionRepository(self.context)
        self.critical_log_repository = CriticalLogRepository()
        self.account_controller = AccountController()

    def refuse_non_positive_amounts(self, amounts_cents):
        for amount_cents in amounts_cents:
            if amount_cents <= 0:
                raise InvalidAmount(amount_cents)

    def refuse_invalid_transfers(self, resolved_transfers):
        for source_account, destination_account, _ in resolved_transfers:
            if source_account.id == destination_account.id:
                raise SameAccount()

            if source_account.event_id != destination_account.event_id:
                raise DifferentEvents()

    def move_money(self, idempotency_key, payment_method, resolved_transfers):
        self.lock_accounts_of(resolved_transfers)
        self.refuse_blocked_accounts(resolved_transfers)

        created_transactions = []
        for leg, (source_account, destination_account, amount_cents) in enumerate(resolved_transfers, start=1):
            self.debit_or_refuse(source_account, amount_cents)
            self.account_repository.credit(destination_account, amount_cents)
            created_transactions.append(
                self.transaction_repository.create_transaction(
                    idempotency_key=idempotency_key,
                    leg=leg,
                    source_account=source_account,
                    destination_account=destination_account,
                    amount_cents=amount_cents,
                    payment_method=payment_method,
                    status=Transaction.SETTLED_STATUS,
                )
            )

        return created_transactions

    def lock_accounts_of(self, resolved_transfers):
        account_ids = []
        for source_account, destination_account, _ in resolved_transfers:
            account_ids.extend([source_account.id, destination_account.id])

        self.account_repository.lock_accounts_in_id_order(account_ids)

    def refuse_blocked_accounts(self, resolved_transfers):
        for source_account, destination_account, _ in resolved_transfers:
            for account in (source_account, destination_account):
                self.session.refresh(account, ["blocked"])
                if account.blocked:
                    self.session.rollback()
                    raise BlockedAccount(account.account_key)

    def debit_or_refuse(self, account, amount_cents):
        try:
            new_balance = self.account_repository.debit_if_balance_allows(account, amount_cents)
        except IntegrityError as integrity_error:
            if BALANCE_CHECK_CONSTRAINT in str(integrity_error.orig):
                self.session.rollback()
                self.critical_log_repository.record(
                    CriticalLogPayment.BALANCE_CHECK_TRIGGERED,
                    account=account,
                    description="the balance CHECK refused a debit that the conditional UPDATE let through",
                )
            raise

        if new_balance is None:
            self.session.rollback()
            raise InsufficientBalance(amount_cents)

    def transactions_already_recorded_after_race(self, integrity_error, idempotency_key):
        self.session.rollback()
        recorded_transactions = self.transaction_repository.list_transactions_by_idempotency_key(idempotency_key)
        if not recorded_transactions:
            raise integrity_error

        return recorded_transactions
