"""The tools StudyOS exposes to MCP clients.

Every handler receives a :class:`ToolContext` carrying the authenticated
`user_id`, and passes it down into `DocumentStore` / the shared study services,
so a connected chat can only ever reach its own account's data.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.api.chat import ChatRequest, run_chat
from app.api.study import StudyRequest, run_study_tool
from app.documents.extraction import DocumentExtractionError
from app.documents.store import DocumentStore
from app.llm.gateway import LLMGateway
from app.llm.models import ModelProfile


MAX_NOTE_CHARACTERS = 200_000


@dataclass(frozen=True, slots=True)
class ToolContext:
    store: DocumentStore
    gateway: LLMGateway
    user_id: str
    resolve_model: Callable[[], tuple[ModelProfile | None, str]]
    """Pick the model for this user: their own configured one, or the managed one.

    Called only by the tools that generate text, so browsing documents keeps
    working for a student who has not configured a model yet.
    """


class ToolError(Exception):
    """A tool failure that should be reported to the model, not the transport."""


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[ToolContext, dict[str, Any]], Awaitable[Any]]
    read_only: bool = True
    destructive: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "title": self.title,
                "readOnlyHint": self.read_only,
                "destructiveHint": self.destructive,
                "openWorldHint": False,
            },
        }


def _schema(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _string(description: str, **extra: Any) -> dict[str, Any]:
    return {"type": "string", "description": description, **extra}


def _document_ids_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "Document ids to use. Call list_documents first to discover them."
        ),
        "minItems": 1,
    }


def _require_str(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"'{key}' is required")
    return value.strip()


def _optional_str(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolError(f"'{key}' must be a string")
    value = value.strip()
    return value or None


def _document_ids(arguments: dict[str, Any], *, required: bool = True) -> list[str]:
    value = arguments.get("document_ids")
    if value is None:
        if required:
            raise ToolError("'document_ids' is required")
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ToolError("'document_ids' must be an array of document id strings")
    ids = [item for item in (item.strip() for item in value) if item]
    if required and not ids:
        raise ToolError("'document_ids' must contain at least one document id")
    return list(dict.fromkeys(ids))


def _int(arguments: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = arguments.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolError(f"'{key}' must be a number")
    return max(low, min(int(value), high))


def _chunk_summary(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": chunk["id"],
        "document_id": chunk["document_id"],
        "filename": chunk["filename"],
        "page_number": chunk.get("page_number"),
        "relevance_score": chunk.get("relevance_score"),
        "text": chunk["text"],
    }


# ----- handlers ---------------------------------------------------------


async def _list_study_sessions(context: ToolContext, arguments: dict[str, Any]) -> Any:
    return {"study_sessions": context.store.list_study_sessions(context.user_id)}


async def _create_study_session(context: ToolContext, arguments: dict[str, Any]) -> Any:
    title = _optional_str(arguments, "title") or "New study session"
    return context.store.create_study_session(title, user_id=context.user_id)


async def _list_documents(context: ToolContext, arguments: dict[str, Any]) -> Any:
    documents = context.store.list_documents(
        _optional_str(arguments, "study_session_id"), user_id=context.user_id
    )
    return {"documents": documents, "count": len(documents)}


async def _get_document(context: ToolContext, arguments: dict[str, Any]) -> Any:
    document = context.store.get_document(
        _require_str(arguments, "document_id"), user_id=context.user_id
    )
    if document is None:
        raise ToolError("Document not found")
    return document


async def _add_note(context: ToolContext, arguments: dict[str, Any]) -> Any:
    title = _require_str(arguments, "title")
    text = _require_str(arguments, "text")
    if len(text) > MAX_NOTE_CHARACTERS:
        raise ToolError(
            f"Note text is too long (limit {MAX_NOTE_CHARACTERS} characters)"
        )
    safe_title = title.replace("/", "-").replace("\\", "-")[:120]
    filename = safe_title if safe_title.endswith(".md") else f"{safe_title}.md"
    try:
        return await context.store.ingest(
            filename=filename,
            content_type="text/markdown",
            content=text.encode("utf-8"),
            study_session_id=_optional_str(arguments, "study_session_id"),
            user_id=context.user_id,
        )
    except DocumentExtractionError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


async def _delete_document(context: ToolContext, arguments: dict[str, Any]) -> Any:
    document_id = _require_str(arguments, "document_id")
    if not await context.store.delete(document_id, user_id=context.user_id):
        raise ToolError("Document not found")
    return {"deleted": True, "document_id": document_id}


async def _search_notes(context: ToolContext, arguments: dict[str, Any]) -> Any:
    query = _require_str(arguments, "query")
    chunks = await context.store.retrieve(
        query,
        document_ids=_document_ids(arguments, required=False) or None,
        limit=_int(arguments, "limit", 5, 1, 20),
        user_id=context.user_id,
    )
    return {
        "query": query,
        "results": [_chunk_summary(chunk) for chunk in chunks],
        "count": len(chunks),
    }


async def _ask_notes(context: ToolContext, arguments: dict[str, Any]) -> Any:
    profile_override, profile_id = context.resolve_model()
    return await run_chat(
        ChatRequest(
            query=_require_str(arguments, "question"),
            document_ids=_document_ids(arguments, required=False) or None,
            session_id=_optional_str(arguments, "session_id"),
            study_session_id=_optional_str(arguments, "study_session_id"),
        ),
        store=context.store,
        gateway=context.gateway,
        user_id=context.user_id,
        profile_override=profile_override,
        profile_id=profile_id,
    )


def _study_handler(tool: str):
    async def handler(context: ToolContext, arguments: dict[str, Any]) -> Any:
        payload = StudyRequest(
            document_ids=_document_ids(arguments),
            topic=_optional_str(arguments, "topic"),
            count=_int(arguments, "count", 8, 1, 20),
            days=_int(arguments, "days", 7, 1, 30),
        )
        profile_override, profile_id = context.resolve_model()
        return await run_study_tool(
            tool,
            payload,
            store=context.store,
            gateway=context.gateway,
            user_id=context.user_id,
            profile_override=profile_override,
            profile_id=profile_id,
        )

    return handler


async def _list_chat_sessions(context: ToolContext, arguments: dict[str, Any]) -> Any:
    return {
        "chat_sessions": context.store.list_chat_sessions(
            _optional_str(arguments, "study_session_id"), user_id=context.user_id
        )
    }


async def _get_chat_session(context: ToolContext, arguments: dict[str, Any]) -> Any:
    chat_session = context.store.get_chat_session(
        _require_str(arguments, "session_id"), user_id=context.user_id
    )
    if chat_session is None:
        raise ToolError("Chat session not found")
    return chat_session


async def _search(context: ToolContext, arguments: dict[str, Any]) -> Any:
    """ChatGPT deep-research compatible search: {results: [{id, title, url}]}."""
    query = _require_str(arguments, "query")
    chunks = await context.store.retrieve(
        query, limit=10, user_id=context.user_id
    )
    return {
        "results": [
            {
                "id": chunk["id"],
                "title": (
                    f"{chunk['filename']}"
                    + (
                        f" (page {chunk['page_number']})"
                        if chunk.get("page_number") is not None
                        else ""
                    )
                ),
                "text": chunk["text"][:400],
                "url": f"studyos://documents/{chunk['document_id']}",
            }
            for chunk in chunks
        ]
    }


async def _fetch(context: ToolContext, arguments: dict[str, Any]) -> Any:
    """ChatGPT deep-research compatible fetch of one chunk or whole document."""
    identifier = _require_str(arguments, "id")
    document_id = identifier.split(":", 1)[0]
    document = context.store.get_document(document_id, user_id=context.user_id)
    if document is None:
        raise ToolError("Document not found")
    chunks = context.store.get_document_chunks(
        document_id, user_id=context.user_id
    )
    if ":" in identifier:
        chunks = [chunk for chunk in chunks if chunk["id"] == identifier] or chunks
    text = "\n\n".join(chunk["text"] for chunk in chunks)
    return {
        "id": identifier,
        "title": document["title"],
        "text": text,
        "url": f"studyos://documents/{document_id}",
        "metadata": {
            "filename": document["filename"],
            "status": document["status"],
            "chunk_count": document.get("chunk_count"),
        },
    }


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="list_study_sessions",
        title="List study sessions",
        description=(
            "List the student's StudyOS study sessions (workspaces). Each one "
            "groups documents and chats for a subject or course."
        ),
        input_schema=_schema({}),
        handler=_list_study_sessions,
    ),
    Tool(
        name="create_study_session",
        title="Create a study session",
        description="Create a new StudyOS study session (workspace).",
        input_schema=_schema(
            {"title": _string("Name for the new study session", maxLength=120)}
        ),
        handler=_create_study_session,
        read_only=False,
    ),
    Tool(
        name="list_documents",
        title="List documents",
        description=(
            "List the student's uploaded course documents with their ids and "
            "indexing status. Use the ids with the other tools."
        ),
        input_schema=_schema(
            {
                "study_session_id": _string(
                    "Only list documents in this study session", default=""
                )
            }
        ),
        handler=_list_documents,
    ),
    Tool(
        name="get_document",
        title="Get a document",
        description="Get one document's metadata and indexing status by id.",
        input_schema=_schema(
            {"document_id": _string("Document id")}, ["document_id"]
        ),
        handler=_get_document,
    ),
    Tool(
        name="add_note",
        title="Add a note",
        description=(
            "Save text as a new markdown document in StudyOS and index it for "
            "retrieval. Use this to store notes written in the chat."
        ),
        input_schema=_schema(
            {
                "title": _string("Title for the note", maxLength=120),
                "text": _string("The note body, as markdown or plain text"),
                "study_session_id": _string(
                    "Study session to file the note under", default=""
                ),
            },
            ["title", "text"],
        ),
        handler=_add_note,
        read_only=False,
    ),
    Tool(
        name="delete_document",
        title="Delete a document",
        description=(
            "Permanently delete one document and its indexed content. "
            "Confirm with the student before calling this."
        ),
        input_schema=_schema(
            {"document_id": _string("Document id")}, ["document_id"]
        ),
        handler=_delete_document,
        read_only=False,
        destructive=True,
    ),
    Tool(
        name="search_notes",
        title="Search notes",
        description=(
            "Hybrid semantic + keyword search over the student's indexed "
            "documents. Returns the matching passages with citations."
        ),
        input_schema=_schema(
            {
                "query": _string("What to search for"),
                "document_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict the search to these documents",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum passages to return (1-20)",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
            },
            ["query"],
        ),
        handler=_search_notes,
    ),
    Tool(
        name="ask_notes",
        title="Ask the notes",
        description=(
            "Ask a question and get an answer grounded in the student's "
            "uploaded notes, with citations. The exchange is saved to their "
            "StudyOS chat history."
        ),
        input_schema=_schema(
            {
                "question": _string("The question to answer from the notes"),
                "document_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict retrieval to these documents",
                },
                "study_session_id": _string(
                    "Study session to record the chat under", default=""
                ),
                "session_id": _string(
                    "Existing chat session id to continue", default=""
                ),
            },
            ["question"],
        ),
        handler=_ask_notes,
        read_only=False,
    ),
    Tool(
        name="generate_summary",
        title="Generate a summary",
        description="Generate a structured study summary from selected documents.",
        input_schema=_schema(
            {
                "document_ids": _document_ids_schema(),
                "topic": _string("Optional focus topic", default=""),
            },
            ["document_ids"],
        ),
        handler=_study_handler("summary"),
        read_only=False,
    ),
    Tool(
        name="generate_flashcards",
        title="Generate flashcards",
        description="Generate active-recall flashcards from selected documents.",
        input_schema=_schema(
            {
                "document_ids": _document_ids_schema(),
                "topic": _string("Optional focus topic", default=""),
                "count": {
                    "type": "integer",
                    "description": "How many flashcards (1-20)",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 8,
                },
            },
            ["document_ids"],
        ),
        handler=_study_handler("flashcards"),
        read_only=False,
    ),
    Tool(
        name="generate_mcqs",
        title="Generate practice questions",
        description=(
            "Generate multiple-choice practice questions with answers and "
            "explanations from selected documents."
        ),
        input_schema=_schema(
            {
                "document_ids": _document_ids_schema(),
                "topic": _string("Optional focus topic", default=""),
                "count": {
                    "type": "integer",
                    "description": "How many questions (1-20)",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 8,
                },
            },
            ["document_ids"],
        ),
        handler=_study_handler("mcq"),
        read_only=False,
    ),
    Tool(
        name="generate_study_plan",
        title="Generate a study plan",
        description="Generate a day-by-day study plan from selected documents.",
        input_schema=_schema(
            {
                "document_ids": _document_ids_schema(),
                "topic": _string("Optional focus topic", default=""),
                "days": {
                    "type": "integer",
                    "description": "Length of the plan in days (1-30)",
                    "minimum": 1,
                    "maximum": 30,
                    "default": 7,
                },
            },
            ["document_ids"],
        ),
        handler=_study_handler("plan"),
        read_only=False,
    ),
    Tool(
        name="list_chat_sessions",
        title="List chat sessions",
        description="List the student's StudyOS chat sessions.",
        input_schema=_schema(
            {
                "study_session_id": _string(
                    "Only list chats in this study session", default=""
                )
            }
        ),
        handler=_list_chat_sessions,
    ),
    Tool(
        name="get_chat_session",
        title="Get a chat session",
        description="Read the messages and citations of one StudyOS chat session.",
        input_schema=_schema(
            {"session_id": _string("Chat session id")}, ["session_id"]
        ),
        handler=_get_chat_session,
    ),
    Tool(
        name="search",
        title="Search",
        description=(
            "Search the student's StudyOS documents and return matching "
            "passages as records that can be retrieved with `fetch`."
        ),
        input_schema=_schema({"query": _string("Search query")}, ["query"]),
        handler=_search,
    ),
    Tool(
        name="fetch",
        title="Fetch",
        description=(
            "Retrieve the full text of a StudyOS document, or of one passage "
            "returned by `search`, by its id."
        ),
        input_schema=_schema(
            {"id": _string("Document id, or a passage id from `search`")},
            ["id"],
        ),
        handler=_fetch,
    ),
)

TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}


async def call_tool(
    name: str, arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    """Run one tool and shape the MCP `tools/call` result."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise ToolError(f"Unknown tool: {name}")
    try:
        result = await tool.handler(context, arguments or {})
    except ToolError:
        raise
    except HTTPException as exc:
        raise ToolError(str(exc.detail)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    text = (
        result
        if isinstance(result, str)
        else json.dumps(result, ensure_ascii=False, indent=2, default=str)
    )
    return {"content": [{"type": "text", "text": text}], "isError": False}
