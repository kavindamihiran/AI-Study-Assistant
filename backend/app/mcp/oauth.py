"""OAuth 2.1 authorization server backing the MCP endpoint.

MCP clients such as Claude and ChatGPT connect over HTTP and authenticate with
an OAuth bearer token, so the backend acts as its own authorization server:
dynamic client registration (RFC 7591), authorization code + PKCE, refresh
token rotation, and opaque tokens stored only as SHA-256 hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from app.database import (
    Database,
    OAuthAuthorizationCodeModel,
    OAuthClientModel,
    OAuthTokenModel,
    UserModel,
)


AUTHORIZATION_CODE_TTL_SECONDS = 300
LOGIN_TICKET_TTL_SECONDS = 900
SUPPORTED_SCOPES = ("studyos.read", "studyos.write")
DEFAULT_SCOPE = " ".join(SUPPORTED_SCOPES)


class OAuthError(Exception):
    """An OAuth error that must be reported with an `error` code."""

    def __init__(
        self,
        error: str,
        description: str = "",
        *,
        status_code: int = 400,
    ) -> None:
        super().__init__(description or error)
        self.error = error
        self.description = description
        self.status_code = status_code

    def to_dict(self) -> dict[str, str]:
        payload = {"error": self.error}
        if self.description:
            payload["error_description"] = self.description
        return payload


@dataclass(frozen=True, slots=True)
class RegisteredClient:
    client_id: str
    client_name: str
    redirect_uris: tuple[str, ...]
    scope: str
    client_uri: str | None
    logo_uri: str | None

    def public_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "client_name": self.client_name,
            "redirect_uris": list(self.redirect_uris),
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class TokenContext:
    """The identity behind a bearer token presented to the MCP endpoint."""

    user_id: str
    client_id: str
    email: str
    display_name: str
    scope: str

    def has_scope(self, scope: str) -> bool:
        return scope in self.scope.split()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def normalize_scope(requested: str | None) -> str:
    """Reduce a requested scope string to the scopes this server grants."""
    if not requested:
        return DEFAULT_SCOPE
    granted = [scope for scope in requested.split() if scope in SUPPORTED_SCOPES]
    return " ".join(granted) if granted else DEFAULT_SCOPE


class OAuthService:
    def __init__(
        self,
        database: Database,
        *,
        signing_secret: str,
        access_token_minutes: int = 60,
        refresh_token_days: int = 30,
    ) -> None:
        self.database = database
        self._signing_secret = (signing_secret or secrets.token_urlsafe(32)).encode(
            "utf-8"
        )
        self.access_token_minutes = max(5, min(access_token_minutes, 1440))
        self.refresh_token_days = max(1, min(refresh_token_days, 365))

    # ----- dynamic client registration --------------------------------

    def register_client(self, payload: dict[str, Any]) -> RegisteredClient:
        redirect_uris = payload.get("redirect_uris")
        if not isinstance(redirect_uris, list) or not redirect_uris:
            raise OAuthError("invalid_redirect_uri", "redirect_uris is required")
        cleaned: list[str] = []
        for uri in redirect_uris:
            if not isinstance(uri, str) or not uri.strip():
                raise OAuthError(
                    "invalid_redirect_uri", "redirect_uris must be strings"
                )
            uri = uri.strip()
            if not uri.startswith(
                ("https://", "http://localhost", "http://127.0.0.1")
            ):
                raise OAuthError(
                    "invalid_redirect_uri",
                    "redirect_uris must use https (or localhost for testing)",
                )
            cleaned.append(uri)
        grant_types = payload.get("grant_types") or [
            "authorization_code",
            "refresh_token",
        ]
        if not isinstance(grant_types, list):
            raise OAuthError("invalid_client_metadata", "grant_types must be a list")
        unsupported = set(grant_types) - {"authorization_code", "refresh_token"}
        if unsupported:
            raise OAuthError(
                "invalid_client_metadata",
                f"Unsupported grant types: {', '.join(sorted(unsupported))}",
            )
        client_name = str(payload.get("client_name") or "MCP client")[:255]
        scope = normalize_scope(payload.get("scope"))
        client = OAuthClientModel(
            id=f"mcp_{uuid.uuid4().hex}",
            client_name=client_name,
            redirect_uris_json=json.dumps(cleaned),
            grant_types_json=json.dumps(sorted(set(grant_types))),
            scope=scope,
            client_uri=str(payload.get("client_uri"))[:512]
            if payload.get("client_uri")
            else None,
            logo_uri=str(payload.get("logo_uri"))[:512]
            if payload.get("logo_uri")
            else None,
            token_endpoint_auth_method="none",
        )
        with self.database.session() as session:
            session.add(client)
        return RegisteredClient(
            client_id=client.id,
            client_name=client_name,
            redirect_uris=tuple(cleaned),
            scope=scope,
            client_uri=client.client_uri,
            logo_uri=client.logo_uri,
        )

    def get_client(self, client_id: str) -> RegisteredClient | None:
        with self.database.session() as session:
            client = session.get(OAuthClientModel, client_id)
            if client is None:
                return None
            return RegisteredClient(
                client_id=client.id,
                client_name=client.client_name,
                redirect_uris=tuple(json.loads(client.redirect_uris_json)),
                scope=client.scope,
                client_uri=client.client_uri,
                logo_uri=client.logo_uri,
            )

    def require_client(self, client_id: str | None) -> RegisteredClient:
        client = self.get_client(client_id) if client_id else None
        if client is None:
            raise OAuthError("invalid_client", "Unknown client_id")
        return client

    # ----- login tickets ----------------------------------------------

    def issue_login_ticket(self, user_id: str) -> str:
        """Bind an authenticated identity to the consent form.

        The consent step is a cross-site form POST, so a SameSite=lax session
        cookie is not sent with it. This signed, short-lived ticket carries the
        identity established on the consent page instead.
        """
        expires_at = int(
            (
                datetime.now(UTC) + timedelta(seconds=LOGIN_TICKET_TTL_SECONDS)
            ).timestamp()
        )
        body = f"{user_id}:{expires_at}"
        signature = hmac.new(
            self._signing_secret, body.encode("utf-8"), hashlib.sha256
        ).digest()
        return f"{body}:{_b64url(signature)}"

    def read_login_ticket(self, ticket: str | None) -> str | None:
        if not ticket:
            return None
        parts = ticket.rsplit(":", 2)
        if len(parts) != 3:
            return None
        user_id, expires_raw, signature = parts
        body = f"{user_id}:{expires_raw}"
        expected = _b64url(
            hmac.new(
                self._signing_secret, body.encode("utf-8"), hashlib.sha256
            ).digest()
        )
        if not hmac.compare_digest(expected, signature):
            return None
        try:
            expires_at = int(expires_raw)
        except ValueError:
            return None
        if expires_at <= int(datetime.now(UTC).timestamp()):
            return None
        return user_id

    # ----- authorization codes -----------------------------------------

    def create_authorization_code(
        self,
        *,
        client_id: str,
        user_id: str,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        scope: str,
        resource: str | None,
    ) -> str:
        code = secrets.token_urlsafe(48)
        now = datetime.now(UTC)
        record = OAuthAuthorizationCodeModel(
            code_hash=_hash(code),
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            resource=resource,
            expires_at=now + timedelta(seconds=AUTHORIZATION_CODE_TTL_SECONDS),
            created_at=now,
        )
        with self.database.session() as session:
            session.add(record)
        return code

    def _consume_authorization_code(
        self, code: str, *, client_id: str, redirect_uri: str, verifier: str
    ) -> tuple[str, str]:
        """Return (user_id, scope) for a valid code, and always delete it.

        The code is deleted before it is validated, so a *failed* exchange
        burns it too: whoever holds a stolen code gets exactly one guess at the
        PKCE verifier rather than an unlimited number within the code's
        five-minute window. A well-behaved client always sends the verifier it
        generated, so this costs nothing in the normal flow.
        """
        code_hash = _hash(code)
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(OAuthAuthorizationCodeModel, code_hash)
            if record is None:
                raise OAuthError("invalid_grant", "Authorization code is invalid")
            user_id = record.user_id
            scope = record.scope
            stored_client = record.client_id
            stored_redirect = record.redirect_uri
            challenge = record.code_challenge
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            session.delete(record)
        if expires_at <= now:
            raise OAuthError("invalid_grant", "Authorization code has expired")
        if stored_client != client_id:
            raise OAuthError(
                "invalid_grant", "Authorization code was issued to another client"
            )
        if stored_redirect != redirect_uri:
            raise OAuthError(
                "invalid_grant",
                "redirect_uri does not match the authorization request",
            )
        expected = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        if not hmac.compare_digest(expected, challenge):
            raise OAuthError("invalid_grant", "PKCE verification failed")
        return user_id, scope

    # ----- tokens -------------------------------------------------------

    def _issue_token_pair(
        self, *, user_id: str, client_id: str, scope: str, grant_id: str
    ) -> dict[str, Any]:
        access_token = secrets.token_urlsafe(48)
        refresh_token = secrets.token_urlsafe(48)
        now = datetime.now(UTC)
        access_expires = now + timedelta(minutes=self.access_token_minutes)
        refresh_expires = now + timedelta(days=self.refresh_token_days)
        with self.database.session() as session:
            session.add(
                OAuthTokenModel(
                    id=uuid.uuid4().hex,
                    token_hash=_hash(access_token),
                    token_type="access",
                    client_id=client_id,
                    user_id=user_id,
                    scope=scope,
                    grant_id=grant_id,
                    expires_at=access_expires,
                    created_at=now,
                )
            )
            session.add(
                OAuthTokenModel(
                    id=uuid.uuid4().hex,
                    token_hash=_hash(refresh_token),
                    token_type="refresh",
                    client_id=client_id,
                    user_id=user_id,
                    scope=scope,
                    grant_id=grant_id,
                    expires_at=refresh_expires,
                    created_at=now,
                )
            )
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": self.access_token_minutes * 60,
            "refresh_token": refresh_token,
            "scope": scope,
        }

    def exchange_authorization_code(
        self,
        *,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        if not code or not redirect_uri or not code_verifier:
            raise OAuthError(
                "invalid_request",
                "code, redirect_uri and code_verifier are required",
            )
        self.require_client(client_id)
        user_id, scope = self._consume_authorization_code(
            code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            verifier=code_verifier,
        )
        return self._issue_token_pair(
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            grant_id=uuid.uuid4().hex,
        )

    def refresh(self, *, refresh_token: str, client_id: str) -> dict[str, Any]:
        if not refresh_token:
            raise OAuthError("invalid_request", "refresh_token is required")
        self.require_client(client_id)
        token_hash = _hash(refresh_token)
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(OAuthTokenModel).where(
                    OAuthTokenModel.token_hash == token_hash,
                    OAuthTokenModel.token_type == "refresh",
                )
            )
            if record is None:
                raise OAuthError("invalid_grant", "Refresh token is invalid")
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            user_id = record.user_id
            scope = record.scope
            grant_id = record.grant_id
            stored_client = record.client_id
            # Rotation: the whole grant is replaced, so retire its tokens.
            session.execute(
                delete(OAuthTokenModel).where(OAuthTokenModel.grant_id == grant_id)
            )
        if expires_at <= now:
            raise OAuthError("invalid_grant", "Refresh token has expired")
        if stored_client != client_id:
            raise OAuthError(
                "invalid_grant", "Refresh token was issued to another client"
            )
        return self._issue_token_pair(
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            grant_id=grant_id,
        )

    def authenticate_token(self, access_token: str | None) -> TokenContext | None:
        if not access_token:
            return None
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(OAuthTokenModel).where(
                    OAuthTokenModel.token_hash == _hash(access_token),
                    OAuthTokenModel.token_type == "access",
                )
            )
            if record is None:
                return None
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                session.delete(record)
                return None
            user = session.get(UserModel, record.user_id)
            if user is None or not user.is_active:
                session.delete(record)
                return None
            record.last_used_at = now
            return TokenContext(
                user_id=user.id,
                client_id=record.client_id,
                email=user.email,
                display_name=user.display_name,
                scope=record.scope,
            )

    def revoke(self, token: str) -> None:
        """Revoke a token and the rest of its grant (RFC 7009)."""
        token_hash = _hash(token)
        with self.database.session() as session:
            record = session.scalar(
                select(OAuthTokenModel).where(
                    OAuthTokenModel.token_hash == token_hash
                )
            )
            if record is None:
                return
            session.execute(
                delete(OAuthTokenModel).where(
                    OAuthTokenModel.grant_id == record.grant_id
                )
            )

    def list_connections(self, user_id: str) -> list[dict[str, Any]]:
        """Connected MCP clients for one user, newest grant first."""
        with self.database.session() as session:
            tokens = list(
                session.scalars(
                    select(OAuthTokenModel)
                    .where(OAuthTokenModel.user_id == user_id)
                    .order_by(OAuthTokenModel.created_at.desc())
                )
            )
            clients = {
                client.id: client
                for client in session.scalars(select(OAuthClientModel))
            }
        # Only access tokens are stamped when used, so "last used" for the
        # connection is the latest use across every token in the grant.
        last_used: dict[str, datetime] = {}
        for token in tokens:
            if token.last_used_at is None:
                continue
            seen = last_used.get(token.grant_id)
            if seen is None or token.last_used_at > seen:
                last_used[token.grant_id] = token.last_used_at
        connections = []
        for record in tokens:
            if record.token_type != "refresh":
                continue
            client = clients.get(record.client_id)
            used_at = last_used.get(record.grant_id)
            connections.append(
                {
                    "grant_id": record.grant_id,
                    "client_id": record.client_id,
                    "client_name": client.client_name
                    if client
                    else "Unknown client",
                    "scope": record.scope,
                    "created_at": record.created_at.isoformat(),
                    "expires_at": record.expires_at.isoformat(),
                    "last_used_at": used_at.isoformat() if used_at else None,
                }
            )
        return connections

    def revoke_grant(self, *, grant_id: str, user_id: str) -> bool:
        with self.database.session() as session:
            result = session.execute(
                delete(OAuthTokenModel).where(
                    OAuthTokenModel.grant_id == grant_id,
                    OAuthTokenModel.user_id == user_id,
                )
            )
            return bool(result.rowcount)

    def purge_expired(self) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            session.execute(
                delete(OAuthAuthorizationCodeModel).where(
                    OAuthAuthorizationCodeModel.expires_at <= now
                )
            )
            session.execute(
                delete(OAuthTokenModel).where(OAuthTokenModel.expires_at <= now)
            )
