import uuid

from sqlalchemy.exc import IntegrityError

from controllers.base_controller import BaseController
from dtos import AccountDTO
from errors import AccountAlreadyExistsInEvent, IdempotencyKeyConflict, InvalidParameter, NotFoundAccount
from repositories import AccountRepository
from utils.integrity_error import violated_constraint_name

ONE_ACCOUNT_PER_EVENT_CONSTRAINTS = ("uq_account_system_kind_per_event", "uq_account_holder_per_event")


class AccountController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.account_repository = AccountRepository(self.context)

    def existing_key_account(self, idempotency_key: str):
        return self.account_repository.get_account_by_idempotency_key(idempotency_key)

    def create_account(self, payload: dict) -> tuple:
        idempotency_key = payload["idempotency_key"]
        account_with_same_key = self.existing_key_account(idempotency_key)

        if account_with_same_key is not None:
            return self._replay(account_with_same_key, payload), False

        try:
            account = self.account_repository.create_account(
                event_id=uuid.UUID(payload["event_id"]),
                holder_id=self._holder_id(payload),
                holder_type=payload.get("holder_type"),
                kind=payload["kind"],
                idempotency_key=idempotency_key,
            )
        except IntegrityError as integrity_error:
            self.session.rollback()
            account_with_same_key = self.existing_key_account(idempotency_key)
            if account_with_same_key is not None:
                return self._replay(account_with_same_key, payload), False
            if violated_constraint_name(integrity_error) in ONE_ACCOUNT_PER_EVENT_CONSTRAINTS:
                raise AccountAlreadyExistsInEvent(payload["event_id"])
            raise

        account_dto = AccountDTO.obj_to_dict(account)
        self.session.commit()
        self.logger.info(f"Account created: {account_dto['id']}, kind={account.kind}")
        return account_dto, True

    def get_account_for_caller(self, account_id: str) -> dict:
        account = self.find_account_owned_by_caller(account_id)
        return AccountDTO.obj_to_dict(account)

    def list_accounts_for_caller(self) -> dict:
        caller_id = self.context.caller_id
        if caller_id is None:
            return {"data": []}

        accounts = self.account_repository.list_accounts_by_holder(caller_id)
        return {"data": AccountDTO.list_to_dict(accounts)}

    def set_account_blocked(self, account_id: str, blocked: bool) -> dict:
        account = self.find_account_or_fail(account_id)
        self.account_repository.update_account_blocked_status(account.id, blocked)

        account_dto = AccountDTO.obj_to_dict(account)
        self.session.commit()
        self.logger.info(f"Account {account_dto['id']} blocked={blocked}")
        return account_dto

    def reconcile_event(self, event_id: str) -> dict:
        event_key = parse_uuid_or_none(event_id)
        if event_key is None:
            raise InvalidParameter(f"event id {event_id} is not a UUID")

        accounts_with_history = self.account_repository.list_accounts_of_event_with_history(event_key)
        return AccountDTO.reconciliation_to_dict(event_key, accounts_with_history)

    def find_account_owned_by_caller(self, account_id: str):
        account = self._find_account_or_none(account_id)
        caller_id = self.context.caller_id
        caller_owns_account = account is not None and caller_id is not None and account.holder_id == caller_id

        if not caller_owns_account:
            raise NotFoundAccount(account_id)

        return account

    def find_account_or_fail(self, account_id: str):
        account = self._find_account_or_none(account_id)
        if account is None:
            raise NotFoundAccount(account_id)

        return account

    def _find_account_or_none(self, account_id: str):
        account_key = parse_uuid_or_none(account_id)
        if account_key is None:
            return None

        return self.account_repository.get_account_by_key(account_key)

    def _replay(self, account, payload: dict) -> dict:
        same_request = (
            account.event_id == uuid.UUID(payload["event_id"])
            and account.holder_id == self._holder_id(payload)
            and account.holder_type == payload.get("holder_type")
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


def parse_uuid_or_none(raw_value: str):
    try:
        return uuid.UUID(raw_value)
    except (TypeError, ValueError):
        return None

    