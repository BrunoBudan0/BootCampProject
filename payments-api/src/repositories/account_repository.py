from uuid import uuid4

from sqlalchemy import text

from database import Context
from models import Account, Transaction


class AccountRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create_account(self, event_id, holder_id, holder_type, kind, idempotency_key):
        account = Account(
            account_key=uuid4(),
            event_id=event_id,
            holder_id=holder_id,
            holder_type=holder_type,
            kind=kind,
            idempotency_key=idempotency_key,
        )

        self.session.add(account)
        self.session.flush()

        return account
    
    
    def update_account_blocked_status(self, account_id, status_blocked):
        account = self.get_account_by_id(account_id)
        if account:
            account.blocked = status_blocked
            self.session.flush()
            return account
        return None


    def get_account_by_idempotency_key(self, idempotency_key):
        return self.session.query(Account).filter_by(idempotency_key=idempotency_key).first()

    def get_account_by_key(self, account_key):
        return self.session.query(Account).filter_by(account_key=account_key).first()

    def get_account_by_id(self, account_id):
        return self.session.query(Account).filter_by(id=account_id).first()

    def list_accounts_by_holder(self, holder_id):
        return (
            self.session.query(Account)
            .filter_by(holder_id=holder_id)
            .order_by(Account.created_at, Account.id)
            .all()
        )

    def get_system_account_of_event(self, event_id, kind):
        return self.session.query(Account).filter_by(event_id=event_id, kind=kind).one_or_none()

    def lock_accounts_in_id_order(self, account_ids):
        self.session.execute(
            text("SELECT id FROM account WHERE id = ANY(:account_ids) ORDER BY id FOR UPDATE"),
            {"account_ids": sorted(set(account_ids))},
        )

    def debit_if_balance_allows(self, account, amount_cents):
        new_balance = self.session.execute(
            text(
                "UPDATE account SET balance_cents = balance_cents - :amount_cents "
                "WHERE id = :account_id AND (kind <> :user_kind OR balance_cents >= :amount_cents) "
                "RETURNING balance_cents"
            ),
            {"amount_cents": amount_cents, "account_id": account.id, "user_kind": Account.USER_KIND},
        ).scalar()
        self.session.expire(account, ["balance_cents"])

        return new_balance

    def credit(self, account, amount_cents):
        new_balance = self.session.execute(
            text(
                "UPDATE account SET balance_cents = balance_cents + :amount_cents "
                "WHERE id = :account_id RETURNING balance_cents"
            ),
            {"amount_cents": amount_cents, "account_id": account.id},
        ).scalar()
        self.session.expire(account, ["balance_cents"])

        return new_balance

    def list_accounts_of_event_with_history(self, event_id):
        return self.session.execute(
            text(
                "SELECT account.account_key, account.kind, account.holder_id, account.balance_cents, "
                "CAST("
                "  COALESCE((SELECT SUM(amount_cents) FROM transaction "
                "            WHERE destination_account_id = account.id AND status = ANY(:moved)), 0) "
                "  - COALESCE((SELECT SUM(amount_cents) FROM transaction "
                "            WHERE source_account_id = account.id AND status = ANY(:moved)), 0) "
                "AS BIGINT) AS history_cents "
                "FROM account WHERE account.event_id = :event_id "
                "ORDER BY account.created_at, account.id"
            ),
            {"event_id": event_id, "moved": list(Transaction.STATUSES_THAT_MOVED_MONEY)},
        ).all()

