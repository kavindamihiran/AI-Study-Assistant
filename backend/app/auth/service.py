from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.database import AuthSessionModel, Database, UserModel


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DUMMY_SALT = bytes.fromhex("00" * 16)
_DUMMY_HASH = hashlib.scrypt(
    b"invalid-password",
    salt=_DUMMY_SALT,
    n=_SCRYPT_N,
    r=_SCRYPT_R,
    p=_SCRYPT_P,
    dklen=32,
)


@dataclass(frozen=True, slots=True)
class AuthContext:
    session_id: str
    user_id: str
    email: str
    display_name: str
    csrf_token: str

    def public_dict(self) -> dict[str, str]:
        return {
            "id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
        }


class AuthService:
    def __init__(self, database: Database, *, session_days: int = 7) -> None:
        self.database = database
        self.session_days = max(1, min(session_days, 30))
        self._failed_logins: dict[str, list[float]] = {}
        self._registration_attempts: dict[str, list[float]] = {}
        self._rate_lock = threading.Lock()

    @staticmethod
    def normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if not _EMAIL.fullmatch(normalized):
            raise ValueError("Enter a valid email address")
        return normalized

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters")
        if len(password) > 128:
            raise ValueError("Password must contain at most 128 characters")

    @staticmethod
    def _derive_password(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=32,
        )

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_user(
        self, *, email: str, password: str, display_name: str
    ) -> UserModel:
        normalized_email = self.normalize_email(email)
        self.validate_password(password)
        clean_name = display_name.strip()
        if not clean_name:
            raise ValueError("Display name is required")
        clean_name = clean_name[:120]
        salt = secrets.token_bytes(16)
        password_hash = self._derive_password(password, salt)
        with self.database.session() as session:
            existing = session.scalar(
                select(UserModel.id).where(
                    UserModel.email == normalized_email
                )
            )
            if existing:
                raise ValueError("An account with this email already exists")
            user = UserModel(
                id=uuid.uuid4().hex,
                email=normalized_email,
                display_name=clean_name,
                password_salt=salt.hex(),
                password_hash=password_hash.hex(),
            )
            session.add(user)
        return user

    def verify_credentials(
        self, *, email: str, password: str
    ) -> UserModel | None:
        try:
            normalized_email = self.normalize_email(email)
        except ValueError:
            normalized_email = email.strip().lower()
        with self.database.session() as session:
            user = session.scalar(
                select(UserModel).where(
                    UserModel.email == normalized_email,
                    UserModel.is_active.is_(True),
                )
            )
            if user is None:
                actual = self._derive_password(password, _DUMMY_SALT)
                hmac.compare_digest(actual, _DUMMY_HASH)
                return None
            actual = self._derive_password(
                password, bytes.fromhex(user.password_salt)
            )
            if not hmac.compare_digest(
                actual, bytes.fromhex(user.password_hash)
            ):
                return None
            return user

    def allow_login_attempt(self, key: str) -> bool:
        now = datetime.now(UTC).timestamp()
        cutoff = now - 15 * 60
        with self._rate_lock:
            attempts = [
                attempt
                for attempt in self._failed_logins.get(key, [])
                if attempt >= cutoff
            ]
            self._failed_logins[key] = attempts
            return len(attempts) < 5

    def record_failed_login(self, key: str) -> None:
        with self._rate_lock:
            self._failed_logins.setdefault(key, []).append(
                datetime.now(UTC).timestamp()
            )

    def clear_failed_logins(self, key: str) -> None:
        with self._rate_lock:
            self._failed_logins.pop(key, None)

    def allow_registration_attempt(self, key: str) -> bool:
        now = datetime.now(UTC).timestamp()
        cutoff = now - 15 * 60
        with self._rate_lock:
            attempts = [
                attempt
                for attempt in self._registration_attempts.get(key, [])
                if attempt >= cutoff
            ]
            self._registration_attempts[key] = attempts
            return len(attempts) < 10

    def record_registration_attempt(self, key: str) -> None:
        with self._rate_lock:
            self._registration_attempts.setdefault(key, []).append(
                datetime.now(UTC).timestamp()
            )

    def create_session(self, user_id: str) -> tuple[str, AuthContext]:
        token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        auth_session = AuthSessionModel(
            id=uuid.uuid4().hex,
            user_id=user_id,
            token_hash=self._token_hash(token),
            csrf_token=csrf_token,
            expires_at=now + timedelta(days=self.session_days),
            created_at=now,
            last_seen_at=now,
        )
        with self.database.session() as session:
            session.add(auth_session)
        context = self.authenticate(token)
        if context is None:
            raise RuntimeError("Authentication session could not be created")
        return token, context

    def authenticate(self, token: str | None) -> AuthContext | None:
        if not token:
            return None
        now = datetime.now(UTC)
        with self.database.session() as session:
            auth_session = session.scalar(
                select(AuthSessionModel).where(
                    AuthSessionModel.token_hash == self._token_hash(token)
                )
            )
            if auth_session is None:
                return None
            expires_at = auth_session.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now or not auth_session.user.is_active:
                session.delete(auth_session)
                return None
            last_seen = auth_session.last_seen_at
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=UTC)
            if now - last_seen > timedelta(minutes=5):
                auth_session.last_seen_at = now
            return AuthContext(
                session_id=auth_session.id,
                user_id=auth_session.user.id,
                email=auth_session.user.email,
                display_name=auth_session.user.display_name,
                csrf_token=auth_session.csrf_token,
            )

    def revoke_session(self, session_id: str) -> None:
        with self.database.session() as session:
            session.execute(
                delete(AuthSessionModel).where(
                    AuthSessionModel.id == session_id
                )
            )
