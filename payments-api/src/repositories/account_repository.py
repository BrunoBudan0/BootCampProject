from uuid import uuid4

from database import Context
from models import Account

class AccountRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create_account(self, event_id, holder_id, kind, idempotency_key):
        account = Account(
            account_key=uuid4(),
            event_id=event_id,
            holder_id=holder_id,
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

