class AccountDTO:
    @staticmethod
    def obj_to_dict(account) -> dict:
        return {
            "id": str(account.account_key),
            "event_id": str(account.event_id),
            "holder_id": str(account.holder_id) if account.holder_id else None,
            "holder_type": account.holder_type,
            "kind": account.kind,
            "balance_cents": account.balance_cents,
            "blocked": account.blocked,
            "created_at": account.created_at.isoformat(),
        }

    @staticmethod
    def list_to_dict(accounts) -> list:
        return [AccountDTO.obj_to_dict(account) for account in accounts]

    @staticmethod
    def reconciliation_to_dict(event_id, accounts_with_history) -> dict:
        accounts = [
            {
                "id": str(account.account_key),
                "kind": account.kind,
                "holder_id": str(account.holder_id) if account.holder_id else None,
                "balance_cents": account.balance_cents,
                "history_cents": account.history_cents,
            }
            for account in accounts_with_history
        ]

        return {
            "event_id": str(event_id),
            "sum_cents": sum(account["balance_cents"] for account in accounts),
            "accounts": accounts,
            "mismatches": [account["id"] for account in accounts if account["balance_cents"] != account["history_cents"]],
        }