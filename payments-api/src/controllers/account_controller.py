import uuid

from sqlalchemy.exc import IntegrityError

from controllers.base_controller import BaseController
from dtos import AccountDTO
from errors import IdempotencyKeyConflict
from repositories import AccountRepository

class AccountController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.account_repository = AccountRepository(self.context)

    def existing_key_account(self, idempotency_key: str):
            return self.account_repository.get_account_by_idempotency_key(idempotency_key)

    def create_account(self, payload: dict) -> tuple:
        idempotency_key = payload["idempotency_key"]
        existing_key_account = self.existing_key_account(idempotency_key)

        if existing_key_account is not None:
            return self._replay(existing_key_account, payload), False
        
        try:
            account = self.account_repository.create_account(
                event_id=uuid.UUID(payload["event_id"]),
                holder_id= self._holder_id(payload),
                kind=payload["kind"],
                idempotency_key=idempotency_key,
            )
        except IntegrityError:
            self.session.rollback()
            existing_key_account = self.existing_key_account(idempotency_key)
            if existing_key_account is None:
                raise 
            return self._replay(existing_key_account, payload), False
        
        account_dto = AccountDTO.obj_to_dict(account)
        self.session.commit()
        self.logger.info(f"Account created: {account_dto['id']}, kind={account.kind}")
        return account_dto, True
    
    def _replay(self, account, payload: dict) -> dict:
        same_request = (
            account.event_id == uuid.UUID(payload["event_id"]) 
            and account.holder_id == self._holder_id(payload)
            and account.kind == payload["kind"]
        )
        if not same_request:
            raise IdempotencyKeyConflict(payload["idempotency_key"])

        self.logger.info(f"Replaying account creation: {account.account_key}, kind={account.kind}")
        return AccountDTO.obj_to_dict(account)

    def _holder_id(self, payload: dict):
        if "holder_id" not in payload:
            return None
        return uuid.UUID(payload["holder_id"])

    