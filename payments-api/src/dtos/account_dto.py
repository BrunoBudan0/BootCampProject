class AccountDTO:
    @staticmethod
    def obj_to_dict(account) -> dict:
        return {
            "id": str(account.account_key),
            "event_id": str(account.event_id),
            "holder_id": str(account.holder_id) if account.holder_id else None,
            "kind": account.kind,
            "balance_cents": account.balance_cents,
            "blocked": account.blocked,
            "created_at": account.created_at.isoformat(),
        }