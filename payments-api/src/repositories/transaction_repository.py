from uuid import uuid4

from sqlalchemy import text

from database import Context
from models import Transaction


class TransactionRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create_transaction(
        self,
        idempotency_key,
        leg,
        source_account,
        destination_account,
        amount_cents,
        payment_method,
        status,
        reversed_transaction=None,
    ):
        transaction = Transaction(
            transaction_key=uuid4(),
            idempotency_key=idempotency_key,
            leg=leg,
            source_account_id=source_account.id,
            destination_account_id=destination_account.id,
            amount_cents=amount_cents,
            payment_method=payment_method,
            status=status,
            reverses_transaction_id=reversed_transaction.id if reversed_transaction else None,
        )

        self.session.add(transaction)
        self.session.flush()

        return transaction

    def list_transactions_by_idempotency_key(self, idempotency_key):
        return (
            self.session.query(Transaction)
            .filter_by(idempotency_key=idempotency_key)
            .order_by(Transaction.leg)
            .all()
        )

    def get_transaction_by_key(self, transaction_key):
        return self.session.query(Transaction).filter_by(transaction_key=transaction_key).first()

    def reload_transaction(self, transaction):
        return self.session.query(Transaction).filter_by(id=transaction.id).populate_existing().one()

    def change_status_if_current(self, transaction, current_status, new_status):
        changed_rows = self.session.execute(
            text("UPDATE transaction SET status = :new_status WHERE id = :transaction_id AND status = :current_status"),
            {"new_status": new_status, "transaction_id": transaction.id, "current_status": current_status},
        ).rowcount
        self.session.expire(transaction, ["status", "updated_at"])

        return changed_rows == 1

    def statement_page(self, account, settled_from, settled_before, limit, offset):
        return self.session.execute(
            text(
                "SELECT transaction_key, payment_method, status, created_at, settled_at, signed_amount, balance_after "
                "FROM ("
                "  SELECT id, transaction_key, payment_method, status, created_at, settled_at,"
                "         CASE WHEN destination_account_id = :account_id THEN amount_cents ELSE -amount_cents END"
                "           AS signed_amount,"
                "         CAST(SUM(CASE WHEN destination_account_id = :account_id THEN amount_cents ELSE -amount_cents END)"
                "              OVER (ORDER BY settled_at, id) AS BIGINT) AS balance_after"
                "  FROM transaction"
                "  WHERE (source_account_id = :account_id OR destination_account_id = :account_id)"
                "    AND status = ANY(:moved)"
                ") AS lines "
                "WHERE (CAST(:settled_from AS TIMESTAMPTZ) IS NULL OR settled_at >= CAST(:settled_from AS TIMESTAMPTZ)) "
                "  AND (CAST(:settled_before AS TIMESTAMPTZ) IS NULL OR settled_at < CAST(:settled_before AS TIMESTAMPTZ)) "
                "ORDER BY settled_at DESC, id DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            {
                "account_id": account.id,
                "moved": list(Transaction.STATUSES_THAT_MOVED_MONEY),
                "settled_from": settled_from,
                "settled_before": settled_before,
                "limit": limit,
                "offset": offset,
            },
        ).all()
