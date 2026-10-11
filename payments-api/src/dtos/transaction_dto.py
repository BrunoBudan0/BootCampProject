class TransactionDTO:
    @staticmethod
    def obj_to_dict(transaction) -> dict:
        reversed_transaction = transaction.reversed_transaction

        return {
            "id": str(transaction.transaction_key),
            "idempotency_key": transaction.idempotency_key,
            "leg": transaction.leg,
            "source_account_id": str(transaction.source_account.account_key),
            "destination_account_id": str(transaction.destination_account.account_key),
            "amount_cents": transaction.amount_cents,
            "payment_method": transaction.payment_method,
            "status": transaction.status,
            "reverses_transaction_id": str(reversed_transaction.transaction_key) if reversed_transaction else None,
            "created_at": transaction.created_at.isoformat(),
        }

    @staticmethod
    def batch_to_dict(idempotency_key, transactions) -> dict:
        return {
            "idempotency_key": idempotency_key,
            "transactions": [TransactionDTO.obj_to_dict(transaction) for transaction in transactions],
        }

    @staticmethod
    def with_pix_charge(transaction, pix_charge) -> dict:
        transaction_dto = TransactionDTO.obj_to_dict(transaction)
        transaction_dto["pix_copy_paste"] = pix_charge.copy_paste if pix_charge else None
        transaction_dto["expires_at"] = pix_charge.expires_at.isoformat() if pix_charge else None

        return transaction_dto

    @staticmethod
    def statement_to_dict(statement_lines, limit, page, is_last_page) -> dict:
        return {
            "data": [
                {
                    "transaction_id": str(line.transaction_key),
                    "payment_method": line.payment_method,
                    "status": line.status,
                    "amount_cents": line.signed_amount,
                    "balance_after_cents": line.balance_after,
                    "created_at": line.created_at.isoformat(),
                    "settled_at": line.settled_at.isoformat(),
                }
                for line in statement_lines
            ],
            "limit": limit,
            "page": page,
            "is_last_page": is_last_page,
        }
