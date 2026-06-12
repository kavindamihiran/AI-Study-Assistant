from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from .service import AuthContext, AuthService


async def require_authenticated_request(request: Request) -> AuthContext:
    auth_service: AuthService = request.app.state.auth_service
    settings = request.app.state.settings
    token = request.cookies.get(settings.auth_cookie_name)
    context = auth_service.authenticate(token)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("X-CSRF-Token", "")
        if not supplied or not hmac.compare_digest(
            supplied, context.csrf_token
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token",
            )
    request.state.auth = context
    return context


def current_auth(request: Request) -> AuthContext:
    context = getattr(request.state, "auth", None)
    if context is None:
        raise RuntimeError("Authentication dependency was not applied")
    return context
