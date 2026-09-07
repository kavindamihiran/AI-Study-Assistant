"""HTTP surface for the MCP server: discovery, OAuth, and the /mcp endpoint."""

from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.api.model_context import resolve_model_for_user
from app.auth import current_auth, require_authenticated_request
from app.auth.service import AuthService

from .oauth import (
    SUPPORTED_SCOPES,
    OAuthError,
    OAuthService,
    normalize_scope,
)
from .protocol import (
    LATEST_PROTOCOL_VERSION,
    PARSE_ERROR,
    SERVER_TITLE,
    error_response,
    handle_message,
)
from .tools import ToolContext


MCP_PATH = "/mcp"
AUTHORIZE_PATH = "/oauth/authorize"
TOKEN_PATH = "/oauth/token"
REGISTER_PATH = "/oauth/register"
REVOKE_PATH = "/oauth/revoke"

_AUTHORIZE_PARAMS = (
    "client_id",
    "redirect_uri",
    "response_type",
    "scope",
    "state",
    "code_challenge",
    "code_challenge_method",
    "resource",
)


# ----- helpers -----------------------------------------------------------


def _oauth_service(request: Request) -> OAuthService:
    service = getattr(request.app.state, "oauth_service", None)
    if service is None:
        raise HTTPException(status_code=404, detail="MCP server is disabled")
    return service


def base_url(request: Request) -> str:
    """The externally reachable origin of this backend.

    `PUBLIC_BASE_URL` wins; otherwise it is reconstructed from the request,
    honouring the proxy headers Render and similar hosts set.
    """
    configured = request.app.state.settings.public_base_url.strip().rstrip("/")
    if configured:
        if not configured.startswith(("http://", "https://")):
            configured = f"https://{configured}"
        return configured
    forwarded_host = request.headers.get("x-forwarded-host")
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{scheme.split(',')[0].strip()}://{host.split(',')[0].strip()}"


def _no_store(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _redirect_with(target: str, params: dict[str, str]) -> RedirectResponse:
    parts = urlparse(target)
    query = f"{parts.query}&{urlencode(params)}" if parts.query else urlencode(params)
    return RedirectResponse(
        urlunparse(parts._replace(query=query)), status_code=302
    )


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #0b1120; color: #e2e8f0; padding: 24px;
    font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
  .card {{ width: 100%; max-width: 420px; background: #111c33; border: 1px solid #1e293b;
    border-radius: 16px; padding: 28px; box-shadow: 0 20px 60px rgba(0,0,0,.45); }}
  h1 {{ font-size: 20px; margin: 0 0 6px; }}
  p {{ color: #94a3b8; margin: 0 0 18px; }}
  .brand {{ font-size: 12px; letter-spacing: .14em; text-transform: uppercase;
    color: #38bdf8; margin-bottom: 14px; }}
  label {{ display: block; font-size: 13px; color: #cbd5f5; margin: 12px 0 6px; }}
  input {{ width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid #24324d;
    background: #0b1120; color: #e2e8f0; font-size: 14px; }}
  input:focus {{ outline: 2px solid #38bdf8; outline-offset: 1px; }}
  button {{ width: 100%; margin-top: 18px; padding: 11px 14px; border: 0; border-radius: 10px;
    background: #38bdf8; color: #06121f; font-weight: 600; font-size: 14px; cursor: pointer; }}
  button.secondary {{ background: transparent; color: #94a3b8; border: 1px solid #24324d;
    margin-top: 10px; }}
  ul {{ margin: 0 0 18px; padding-left: 18px; color: #cbd5f5; font-size: 14px; }}
  li {{ margin-bottom: 6px; }}
  .error {{ background: #3f1d2b; border: 1px solid #7f1d3a; color: #fecdd3;
    padding: 10px 12px; border-radius: 10px; font-size: 13px; margin-bottom: 14px; }}
  .account {{ font-size: 13px; color: #94a3b8; margin-top: 16px; }}
</style></head>
<body><div class="card"><div class="brand">{html.escape(SERVER_TITLE)}</div>{body}</div></body></html>"""


def _hidden_fields(params: dict[str, str], extra: dict[str, str]) -> str:
    fields = {**params, **extra}
    return "".join(
        f'<input type="hidden" name="{html.escape(key)}" '
        f'value="{html.escape(value)}">'
        for key, value in fields.items()
        if value
    )


def _error_page(title: str, message: str, status_code: int = 400) -> HTMLResponse:
    body = (
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(message)}</p>"
    )
    return HTMLResponse(_page(title, body), status_code=status_code)


def _consent_page(
    *,
    client_name: str,
    account_email: str,
    params: dict[str, str],
    login_ticket: str,
    scope: str,
) -> HTMLResponse:
    scope_items = "".join(
        f"<li>{html.escape(_SCOPE_LABELS.get(item, item))}</li>"
        for item in scope.split()
    )
    body = f"""
      <h1>Connect {html.escape(client_name)}?</h1>
      <p>{html.escape(client_name)} is asking to use your StudyOS account.</p>
      <ul>{scope_items}</ul>
      <form method="post" action="{AUTHORIZE_PATH}">
        {_hidden_fields(params, {"login_ticket": login_ticket, "action": "approve"})}
        <button type="submit">Allow access</button>
      </form>
      <form method="post" action="{AUTHORIZE_PATH}">
        {_hidden_fields(params, {"login_ticket": login_ticket, "action": "deny"})}
        <button class="secondary" type="submit">Cancel</button>
      </form>
      <p class="account">Signed in as {html.escape(account_email)}</p>
    """
    return HTMLResponse(_page("Connect to StudyOS", body))


def _login_page(
    *,
    client_name: str,
    params: dict[str, str],
    error: str = "",
    email: str = "",
) -> HTMLResponse:
    body = f"""
      <h1>Sign in to StudyOS</h1>
      <p>Sign in to connect {html.escape(client_name)} to your account.</p>
      {f'<div class="error">{html.escape(error)}</div>' if error else ""}
      <form method="post" action="{AUTHORIZE_PATH}">
        {_hidden_fields(params, {"action": "login"})}
        <label for="email">Email</label>
        <input id="email" name="email" type="email" autocomplete="username"
          value="{html.escape(email)}" required>
        <label for="password">Password</label>
        <input id="password" name="password" type="password"
          autocomplete="current-password" required>
        <button type="submit">Sign in</button>
      </form>
    """
    return HTMLResponse(_page("Sign in to StudyOS", body))


_SCOPE_LABELS = {
    "studyos.read": "Read your study sessions, documents and chats",
    "studyos.write": (
        "Add notes, ask questions and generate study material in your account"
    ),
}


# ----- routers -----------------------------------------------------------

metadata_router = APIRouter(tags=["mcp"], include_in_schema=False)
oauth_router = APIRouter(prefix="/oauth", tags=["mcp"], include_in_schema=False)
mcp_router = APIRouter(tags=["mcp"], include_in_schema=False)
connections_router = APIRouter(
    prefix="/api/mcp",
    tags=["mcp"],
    dependencies=[Depends(require_authenticated_request)],
)


def _protected_resource_metadata(request: Request) -> dict[str, Any]:
    root = base_url(request)
    return {
        "resource": f"{root}{MCP_PATH}",
        "authorization_servers": [root],
        "scopes_supported": list(SUPPORTED_SCOPES),
        "bearer_methods_supported": ["header"],
        "resource_name": SERVER_TITLE,
        "resource_documentation": f"{root}/docs",
    }


def _authorization_server_metadata(request: Request) -> dict[str, Any]:
    root = base_url(request)
    return {
        "issuer": root,
        "authorization_endpoint": f"{root}{AUTHORIZE_PATH}",
        "token_endpoint": f"{root}{TOKEN_PATH}",
        "registration_endpoint": f"{root}{REGISTER_PATH}",
        "revocation_endpoint": f"{root}{REVOKE_PATH}",
        "scopes_supported": list(SUPPORTED_SCOPES),
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "service_documentation": f"{root}/docs",
    }


@metadata_router.get("/.well-known/oauth-protected-resource")
@metadata_router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata(request: Request) -> JSONResponse:
    _oauth_service(request)
    return _no_store(_protected_resource_metadata(request))


@metadata_router.get("/.well-known/oauth-authorization-server")
@metadata_router.get("/.well-known/oauth-authorization-server/mcp")
@metadata_router.get("/.well-known/openid-configuration")
async def authorization_server_metadata(request: Request) -> JSONResponse:
    _oauth_service(request)
    return _no_store(_authorization_server_metadata(request))


@oauth_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_client(request: Request) -> JSONResponse:
    service = _oauth_service(request)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return _no_store(
            {"error": "invalid_client_metadata", "error_description": "Body must be JSON"},
            status_code=400,
        )
    if not isinstance(payload, dict):
        return _no_store(
            {"error": "invalid_client_metadata", "error_description": "Body must be an object"},
            status_code=400,
        )
    try:
        client = service.register_client(payload)
    except OAuthError as exc:
        return _no_store(exc.to_dict(), status_code=exc.status_code)
    return _no_store(client.public_dict(), status_code=201)


def _validate_authorize_request(
    request: Request, params: dict[str, str]
) -> tuple[Any, str, str] | HTMLResponse | RedirectResponse:
    """Return (client, redirect_uri, scope) or an error response."""
    service = _oauth_service(request)
    try:
        client = service.require_client(params.get("client_id"))
    except OAuthError as exc:
        return _error_page("Cannot connect", exc.description or exc.error)

    redirect_uri = params.get("redirect_uri") or ""
    if not redirect_uri and len(client.redirect_uris) == 1:
        redirect_uri = client.redirect_uris[0]
    if redirect_uri not in client.redirect_uris:
        return _error_page(
            "Cannot connect",
            "The redirect_uri does not match the one this client registered.",
        )

    state = params.get("state", "")
    if params.get("response_type") != "code":
        return _redirect_with(
            redirect_uri,
            {
                "error": "unsupported_response_type",
                "error_description": "Only response_type=code is supported",
                **({"state": state} if state else {}),
            },
        )
    if not params.get("code_challenge"):
        return _redirect_with(
            redirect_uri,
            {
                "error": "invalid_request",
                "error_description": "PKCE is required (code_challenge)",
                **({"state": state} if state else {}),
            },
        )
    if params.get("code_challenge_method", "S256") != "S256":
        return _redirect_with(
            redirect_uri,
            {
                "error": "invalid_request",
                "error_description": "code_challenge_method must be S256",
                **({"state": state} if state else {}),
            },
        )
    return client, redirect_uri, normalize_scope(params.get("scope"))


@oauth_router.get("/authorize")
async def authorize(request: Request) -> Response:
    service = _oauth_service(request)
    params = {
        key: request.query_params.get(key, "") for key in _AUTHORIZE_PARAMS
    }
    validated = _validate_authorize_request(request, params)
    if isinstance(validated, Response):
        return validated
    client, redirect_uri, scope = validated
    params["redirect_uri"] = redirect_uri
    params["scope"] = scope

    auth_service: AuthService = request.app.state.auth_service
    cookie_name = request.app.state.settings.auth_cookie_name
    context = auth_service.authenticate(request.cookies.get(cookie_name))
    if context is None:
        return _login_page(client_name=client.client_name, params=params)
    return _consent_page(
        client_name=client.client_name,
        account_email=context.email,
        params=params,
        login_ticket=service.issue_login_ticket(context.user_id),
        scope=scope,
    )


@oauth_router.post("/authorize")
async def authorize_submit(request: Request) -> Response:
    service = _oauth_service(request)
    form = await request.form()
    params = {key: str(form.get(key, "") or "") for key in _AUTHORIZE_PARAMS}
    validated = _validate_authorize_request(request, params)
    if isinstance(validated, Response):
        return validated
    client, redirect_uri, scope = validated
    params["redirect_uri"] = redirect_uri
    params["scope"] = scope
    state = params.get("state", "")

    action = str(form.get("action") or "")
    if action == "deny":
        return _redirect_with(
            redirect_uri,
            {
                "error": "access_denied",
                "error_description": "The student declined the connection",
                **({"state": state} if state else {}),
            },
        )

    user_id = service.read_login_ticket(str(form.get("login_ticket") or ""))
    email = str(form.get("email") or "").strip()
    if user_id is None and email:
        password = str(form.get("password") or "")
        auth_service: AuthService = request.app.state.auth_service
        rate_key = f"mcp:{email.lower()}"
        if not auth_service.allow_login_attempt(rate_key):
            return _login_page(
                client_name=client.client_name,
                params=params,
                error="Too many attempts. Try again in a few minutes.",
                email=email,
            )
        user = auth_service.verify_credentials(email=email, password=password)
        if user is None:
            auth_service.record_failed_login(rate_key)
            return _login_page(
                client_name=client.client_name,
                params=params,
                error="Incorrect email or password.",
                email=email,
            )
        auth_service.clear_failed_logins(rate_key)
        user_id = user.id

    if user_id is None:
        return _login_page(
            client_name=client.client_name,
            params=params,
            error="Your sign-in expired. Please sign in again.",
        )

    if action != "approve":
        return _consent_page(
            client_name=client.client_name,
            account_email=email or "your StudyOS account",
            params=params,
            login_ticket=service.issue_login_ticket(user_id),
            scope=scope,
        )

    code = service.create_authorization_code(
        client_id=client.client_id,
        user_id=user_id,
        redirect_uri=redirect_uri,
        code_challenge=params["code_challenge"],
        code_challenge_method="S256",
        scope=scope,
        resource=params.get("resource") or None,
    )
    return _redirect_with(
        redirect_uri, {"code": code, **({"state": state} if state else {})}
    )


async def _token_form(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            payload = await request.json()
        except (json.JSONDecodeError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {key: str(value) for key, value in payload.items()}
    form = await request.form()
    return {key: str(value) for key, value in form.items()}


@oauth_router.post("/token")
async def token(request: Request) -> JSONResponse:
    service = _oauth_service(request)
    form = await _token_form(request)
    grant_type = form.get("grant_type", "")
    try:
        if grant_type == "authorization_code":
            payload = service.exchange_authorization_code(
                code=form.get("code", ""),
                client_id=form.get("client_id", ""),
                redirect_uri=form.get("redirect_uri", ""),
                code_verifier=form.get("code_verifier", ""),
            )
        elif grant_type == "refresh_token":
            payload = service.refresh(
                refresh_token=form.get("refresh_token", ""),
                client_id=form.get("client_id", ""),
            )
        else:
            raise OAuthError(
                "unsupported_grant_type",
                "Supported grants: authorization_code, refresh_token",
            )
    except OAuthError as exc:
        return _no_store(exc.to_dict(), status_code=exc.status_code)
    return _no_store(payload)


@oauth_router.post("/revoke")
async def revoke(request: Request) -> Response:
    service = _oauth_service(request)
    form = await _token_form(request)
    token_value = form.get("token", "")
    if token_value:
        service.revoke(token_value)
    # RFC 7009: an unknown token is still a success.
    return Response(status_code=200, headers={"Cache-Control": "no-store"})


# ----- the MCP endpoint --------------------------------------------------


def _unauthorized(request: Request, description: str) -> JSONResponse:
    resource_metadata = (
        f"{base_url(request)}/.well-known/oauth-protected-resource"
    )
    return JSONResponse(
        {"error": "invalid_token", "error_description": description},
        status_code=401,
        headers={
            "WWW-Authenticate": (
                'Bearer error="invalid_token", '
                f'error_description="{description}", '
                f'resource_metadata="{resource_metadata}"'
            )
        },
    )


@mcp_router.post(MCP_PATH)
async def mcp_endpoint(request: Request) -> Response:
    service = _oauth_service(request)
    token_context = service.authenticate_token(_bearer_token(request))
    if token_context is None:
        return _unauthorized(
            request, "A valid StudyOS access token is required"
        )

    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(
            error_response(None, PARSE_ERROR, "Request body must be JSON"),
            status_code=400,
        )

    context = ToolContext(
        store=request.app.state.document_store,
        gateway=request.app.state.llm_gateway,
        user_id=token_context.user_id,
        resolve_model=lambda: resolve_model_for_user(
            request, token_context.user_id
        ),
    )
    headers = {"MCP-Protocol-Version": LATEST_PROTOCOL_VERSION}

    if isinstance(payload, list):
        responses = [
            response
            for response in [
                await handle_message(message, context) for message in payload
            ]
            if response is not None
        ]
        if not responses:
            return Response(status_code=202, headers=headers)
        return JSONResponse(responses, headers=headers)

    response = await handle_message(payload, context)
    if response is None:
        return Response(status_code=202, headers=headers)
    return JSONResponse(response, headers=headers)


@mcp_router.get(MCP_PATH)
async def mcp_stream_not_supported(request: Request) -> Response:
    """This server never pushes messages, so it offers no SSE stream."""
    _oauth_service(request)
    if _bearer_token(request) is None:
        return _unauthorized(request, "A valid StudyOS access token is required")
    return Response(status_code=405, headers={"Allow": "POST, DELETE"})


@mcp_router.delete(MCP_PATH)
async def mcp_session_end(request: Request) -> Response:
    """Sessions are stateless, so there is nothing to tear down."""
    _oauth_service(request)
    return Response(status_code=204)


# ----- account management for the web app --------------------------------


@connections_router.get("/connections")
async def list_connections(request: Request) -> dict[str, Any]:
    service = _oauth_service(request)
    return {
        "connections": service.list_connections(current_auth(request).user_id)
    }


@connections_router.delete(
    "/connections/{grant_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_connection(grant_id: str, request: Request) -> None:
    service = _oauth_service(request)
    if not service.revoke_grant(
        grant_id=grant_id, user_id=current_auth(request).user_id
    ):
        raise HTTPException(status_code=404, detail="Connection not found")


ROUTERS = (metadata_router, oauth_router, mcp_router, connections_router)
