"""Remote MCP server: lets Claude, ChatGPT and other MCP clients use StudyOS."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .oauth import OAuthError, OAuthService, TokenContext
from .protocol import SERVER_VERSION, SUPPORTED_PROTOCOL_VERSIONS
from .routes import MCP_PATH, ROUTERS

__all__ = [
    "MCP_PATH",
    "MCPCorsMiddleware",
    "OAuthError",
    "OAuthService",
    "ROUTERS",
    "SERVER_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "TokenContext",
]


_OPEN_PREFIXES = (
    "/mcp",
    "/.well-known/",
    "/oauth/register",
    "/oauth/token",
    "/oauth/revoke",
)
_ALLOW_HEADERS = (
    "authorization, content-type, mcp-protocol-version, mcp-session-id, "
    "last-event-id"
)
_EXPOSE_HEADERS = "mcp-protocol-version, mcp-session-id, www-authenticate"


class MCPCorsMiddleware:
    """Wide-open CORS for the MCP and OAuth machinery only.

    Browser-based MCP clients fetch these endpoints from their own origin with
    a bearer token (never a cookie), so `*` is safe here — unlike the app's own
    credentialed API, which keeps its narrow allow-list.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _is_open_path(path: str) -> bool:
        return any(
            path == prefix or path.startswith(prefix)
            for prefix in _OPEN_PREFIXES
        )

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http" or not self._is_open_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        if scope["method"] == "OPTIONS":
            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": [
                        (b"access-control-allow-origin", b"*"),
                        (b"access-control-allow-methods", b"GET, POST, DELETE, OPTIONS"),
                        (b"access-control-allow-headers", _ALLOW_HEADERS.encode()),
                        (b"access-control-max-age", b"86400"),
                        (b"content-length", b"0"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if not key.lower().startswith(b"access-control-")
                ]
                headers.append((b"access-control-allow-origin", b"*"))
                headers.append(
                    (b"access-control-expose-headers", _EXPOSE_HEADERS.encode())
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cors)
