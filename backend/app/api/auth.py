from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.auth import (
    AuthContext,
    AuthService,
    current_auth,
    require_authenticated_request,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


def _set_session_cookie(
    request: Request, response: Response, token: str
) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )


def _auth_response(context: AuthContext) -> dict:
    return {
        "user": context.public_dict(),
        "csrf_token": context.csrf_token,
    }


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, request: Request, response: Response
) -> dict:
    settings = request.app.state.settings
    if not settings.auth_registration_enabled:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    auth_service: AuthService = request.app.state.auth_service
    ip_key = f"ip:{_client_ip(request)}"
    email_key = f"email:{payload.email.strip().lower()}"
    if (
        not auth_service.allow_registration_attempt(ip_key)
        or not auth_service.allow_registration_attempt(email_key)
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many registration attempts. Try again later.",
        )
    auth_service.record_registration_attempt(ip_key)
    auth_service.record_registration_attempt(email_key)
    try:
        user = auth_service.create_user(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        message = str(exc)
        code = 409 if "already exists" in message else 400
        raise HTTPException(status_code=code, detail=message) from exc
    token, context = auth_service.create_session(user.id)
    _set_session_cookie(request, response, token)
    return _auth_response(context)


@router.post("/login")
async def login(
    payload: LoginRequest, request: Request, response: Response
) -> dict:
    auth_service: AuthService = request.app.state.auth_service
    rate_key = payload.email.strip().lower()
    if not auth_service.allow_login_attempt(rate_key):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
        )
    user = auth_service.verify_credentials(
        email=payload.email, password=payload.password
    )
    if user is None:
        auth_service.record_failed_login(rate_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    auth_service.clear_failed_logins(rate_key)
    token, context = auth_service.create_session(user.id)
    _set_session_cookie(request, response, token)
    return _auth_response(context)


@router.get("/me", dependencies=[Depends(require_authenticated_request)])
async def me(request: Request) -> dict:
    return _auth_response(current_auth(request))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_authenticated_request)],
)
async def logout(request: Request, response: Response) -> None:
    context = current_auth(request)
    auth_service: AuthService = request.app.state.auth_service
    auth_service.revoke_session(context.session_id)
    settings = request.app.state.settings
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )
