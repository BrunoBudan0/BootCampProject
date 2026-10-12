import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from connectors import UsersConnector
from constants import SESSION_TTL_HOURS
from controllers.base_controller import BaseController
from errors import NotAuthenticated
from models import Session
from repositories import SessionRepository


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.sessions = SessionRepository(self.session)

    def login(self, payload: dict) -> dict:
        identity = UsersConnector().login(payload["email"], payload["password"], payload["user_type"])

        # O token só existe na resposta; o banco guarda o hash.
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)

        user_id = uuid.UUID(str(identity["id"]))

        row = Session(
            token_hash=hash_token(token),
            user_id=user_id,
            user_type=identity["user_type"],
            expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
            created_at=now,
        )
        self.sessions.add(row)
        self.session.commit()

        self.logger.info(f"sessão aberta para {identity['user_type']} {user_id}")
        return {
            "token": token,
            "user_id": str(user_id),
            "user_type": identity["user_type"],
            "expires_at": row.expires_at.isoformat(),
        }

    def authenticate(self, token: str | None) -> Session:
        if not token:
            raise NotAuthenticated()
        session = self.sessions.find_valid(hash_token(token), datetime.now(timezone.utc))
        if session is None:
            raise NotAuthenticated()
        return session
