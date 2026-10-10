from base_controller import BaseController


class AccountController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.account_repository = AccountRepository(self.context)

    def create_account(self, payload: dict) -> tuple:

        existing_account = self.account_repository.get_account_by_idempotency_key(idempotency_key)
        # Deveria ter os logs de sistema, para ficar no log do docker
        if existing_account:
            return existing_account, 200

        account = self.account_repository.create_account(event_id, holder_id, kind, idempotency_key)
        return account
        