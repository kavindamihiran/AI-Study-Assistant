"""JSON-RPC 2.0 dispatch for the Model Context Protocol.

The server is stateless: every HTTP POST carries a complete JSON-RPC message
and gets a complete JSON response back, which is all the Streamable HTTP
transport requires of a server that does not push server-initiated messages.
"""

from __future__ import annotations

from typing import Any

from .tools import TOOLS, ToolContext, ToolError, call_tool


SERVER_NAME = "studyos"
SERVER_TITLE = "StudyOS"
SERVER_VERSION = "0.1.0"
LATEST_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)

INSTRUCTIONS = (
    "StudyOS holds the student's uploaded course documents and study "
    "workspaces. Call list_documents to discover document ids before using "
    "the tools that take them. Prefer search_notes or ask_notes for questions "
    "about the material so answers stay grounded in the student's own notes, "
    "and cite the filename and page returned with each passage. Ask the "
    "student to confirm before deleting anything."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JSONRPCError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(
    request_id: Any, code: int, message: str
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _negotiate_protocol_version(params: dict[str, Any]) -> str:
    requested = params.get("protocolVersion")
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return LATEST_PROTOCOL_VERSION


async def handle_message(
    message: Any, context: ToolContext
) -> dict[str, Any] | None:
    """Handle one JSON-RPC message; returns None for notifications."""
    if not isinstance(message, dict):
        return error_response(None, INVALID_REQUEST, "Request must be an object")
    request_id = message.get("id")
    method = message.get("method")
    is_notification = "id" not in message
    if not isinstance(method, str):
        if is_notification:
            return None
        return error_response(request_id, INVALID_REQUEST, "Missing method")
    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return error_response(request_id, INVALID_PARAMS, "params must be an object")

    try:
        result = await _dispatch(method, params, context)
    except JSONRPCError as exc:
        if is_notification:
            return None
        return error_response(request_id, exc.code, exc.message)
    except Exception as exc:  # noqa: BLE001 - never leak a traceback to a client
        if is_notification:
            return None
        return error_response(
            request_id, INTERNAL_ERROR, f"Internal server error: {exc}"
        )
    if result is None or is_notification:
        return None
    return _result(request_id, result)


async def _dispatch(
    method: str, params: dict[str, Any], context: ToolContext
) -> dict[str, Any] | None:
    if method == "initialize":
        return {
            "protocolVersion": _negotiate_protocol_version(params),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": SERVER_NAME,
                "title": SERVER_TITLE,
                "version": SERVER_VERSION,
            },
            "instructions": INSTRUCTIONS,
        }
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [tool.public_dict() for tool in TOOLS]}
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str):
            raise JSONRPCError(INVALID_PARAMS, "Tool name is required")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise JSONRPCError(INVALID_PARAMS, "arguments must be an object")
        try:
            return await call_tool(name, arguments, context)
        except ToolError as exc:
            # Tool failures belong in the result so the model can react to them.
            return {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            }
    if method == "resources/list":
        return {"resources": []}
    if method == "resources/templates/list":
        return {"resourceTemplates": []}
    if method == "prompts/list":
        return {"prompts": []}
    raise JSONRPCError(METHOD_NOT_FOUND, f"Method not found: {method}")
