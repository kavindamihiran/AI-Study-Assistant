from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.documents.store import DocumentStore
from app.auth import current_auth, require_authenticated_request
from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage, ModelProfile, NormalizedLLMResponse

from .model_context import resolve_model_for_user


router = APIRouter(
    prefix="/api/study",
    tags=["study"],
    dependencies=[Depends(require_authenticated_request)],
)


class StudyRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    topic: str | None = Field(default=None, max_length=2000)
    count: int = Field(default=8, ge=1, le=20)
    days: int = Field(default=7, ge=1, le=30)


class MCQItem(BaseModel):
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=6)
    answer_index: int = Field(ge=0)
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def answer_must_reference_an_option(self) -> "MCQItem":
        if self.answer_index >= len(self.options):
            raise ValueError("answer_index must reference an option")
        return self


class MCQPayload(BaseModel):
    items: list[MCQItem]


class FlashcardItem(BaseModel):
    front: str = Field(min_length=1)
    back: str = Field(min_length=1)


class FlashcardPayload(BaseModel):
    items: list[FlashcardItem]


def _context_text(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for index, chunk in enumerate(chunks, start=1):
        page = (
            f", page {chunk['page_number']}"
            if chunk.get("page_number") is not None
            else ""
        )
        parts.append(
            f"[Source {index}: {chunk['filename']}{page}]\n{chunk['text']}"
        )
    return "\n\n".join(parts)


def _citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None]] = set()
    for chunk in chunks:
        key = (chunk["document_id"], chunk.get("page_number"))
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "document_id": chunk["document_id"],
                "filename": chunk["filename"],
                "page_number": chunk.get("page_number"),
                "chunk_id": chunk["id"],
                "quoted_snippet": chunk["text"][:240],
                "relevance_score": chunk.get("relevance_score", 0.5),
            }
        )
        if len(citations) == 12:
            break
    return citations


def _normalize_items(parsed: Any, aliases: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(parsed, list):
        return {"items": parsed}
    if isinstance(parsed, dict):
        if isinstance(parsed.get("items"), list):
            return {"items": parsed["items"]}
        for alias in aliases:
            if isinstance(parsed.get(alias), list):
                return {"items": parsed[alias]}
    raise ValueError("The AI assistant did not return a valid item list")


def _record_run(
    store: DocumentStore,
    result: NormalizedLLMResponse,
    profile_id: str,
    tool: str,
    user_id: str,
) -> None:
    store.record_model_run(
        session_id=None,
        profile_id=result.profile_id or profile_id,
        latency_ms=result.latency_ms,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        status="success" if result.ok else "error",
        error_message=result.error_message,
        retry_count=result.retry_count,
        graph_node_name=f"study_{tool}",
        user_id=user_id,
    )


async def run_study_tool(
    tool: Literal["summary", "mcq", "flashcards", "plan"],
    payload: StudyRequest,
    *,
    store: DocumentStore,
    gateway: LLMGateway,
    user_id: str,
    profile_override: ModelProfile | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Generate one study artefact from the user's indexed notes.

    Shared by the HTTP routes and the MCP server so both stay in sync.
    Failures are raised as HTTPException; the MCP layer maps them to tool errors.
    ``profile_override`` carries the model the student configured for themselves;
    without one the server-managed profile generates the material.
    """
    profile_id = profile_id or gateway.active_profile_id
    override_id = None if profile_override else profile_id
    focus = payload.topic.strip() if payload.topic and payload.topic.strip() else None
    chunks = await store.get_study_chunks(
        document_ids=list(dict.fromkeys(payload.document_ids)),
        focus=focus,
        user_id=user_id,
    )
    if not chunks:
        raise HTTPException(
            status_code=422,
            detail="No indexed content was found in the selected documents.",
        )

    focus_instruction = (
        f"Give extra attention to this focus while still covering the notes broadly: {focus}"
        if focus
        else "Cover the full breadth of the supplied notes."
    )
    context = _context_text(chunks)
    system = ChatMessage(
        "system",
        "You create study material using only supplied notes. Never invent facts.",
    )
    data: dict[str, Any] | None = None

    if tool == "summary":
        prompt = (
            "Create a comprehensive but readable study summary. Use headings and "
            "bullet points, include definitions, relationships, processes, examples, "
            "and important details present in the notes. "
            f"{focus_instruction}\n\nNOTES:\n{context}"
        )
        result = await gateway.generate_text(
            [system, ChatMessage("user", prompt)],
            profile_id=override_id,
            profile_override=profile_override,
            max_tokens=3000,
        )
        text = result.text
    elif tool == "plan":
        prompt = (
            f"Create a practical {payload.days}-day study plan based only on these "
            "notes. For each day include topics, an active-recall task, a practice "
            "task, and a short review checkpoint. "
            f"{focus_instruction}\n\nNOTES:\n{context}"
        )
        result = await gateway.generate_text(
            [system, ChatMessage("user", prompt)],
            profile_id=override_id,
            profile_override=profile_override,
            max_tokens=2600,
        )
        text = result.text
    elif tool == "mcq":
        prompt = (
            f"Create exactly {payload.count} multiple-choice questions covering the "
            "important material in the notes. Include conceptual and applied questions. "
            f"{focus_instruction}\n\n"
            'Return {"items":[{"question":"...","options":["..."],'
            '"answer_index":0,"explanation":"..."}]}. '
            "answer_index is zero-based.\n\n"
            f"NOTES:\n{context}"
        )
        result = await gateway.generate_json(
            [system, ChatMessage("user", prompt)],
            profile_id=override_id,
            profile_override=profile_override,
            max_tokens=3500,
        )
        text = ""
        if result.ok:
            try:
                data = MCQPayload.model_validate(
                    _normalize_items(result.parsed_json, ("mcqs", "questions"))
                ).model_dump()
            except (ValidationError, ValueError) as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"The AI assistant returned invalid MCQ data: {exc}",
                ) from exc
    else:
        prompt = (
            f"Create exactly {payload.count} high-value active-recall flashcards from "
            "the notes. Keep fronts specific and backs concise but complete. "
            f"{focus_instruction}\n\n"
            'Return {"items":[{"front":"...","back":"..."}]}.\n\n'
            f"NOTES:\n{context}"
        )
        result = await gateway.generate_json(
            [system, ChatMessage("user", prompt)],
            profile_id=override_id,
            profile_override=profile_override,
            max_tokens=3000,
        )
        text = ""
        if result.ok:
            try:
                data = FlashcardPayload.model_validate(
                    _normalize_items(result.parsed_json, ("flashcards", "cards"))
                ).model_dump()
            except (ValidationError, ValueError) as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"The AI assistant returned invalid flashcard data: {exc}",
                ) from exc

    _record_run(store, result, profile_id, tool, user_id)
    if not result.ok:
        raise HTTPException(
            status_code=502,
            detail="The AI assistant is temporarily unavailable. Please try again.",
        )

    return {
        "tool": tool,
        "text": text,
        "data": data,
        "citations": _citations(chunks),
        "latency_ms": result.latency_ms,
    }


async def _generate(
    tool: Literal["summary", "mcq", "flashcards", "plan"],
    payload: StudyRequest,
    request: Request,
) -> dict[str, Any]:
    user_id = current_auth(request).user_id
    profile_override, profile_id = resolve_model_for_user(request, user_id)
    return await run_study_tool(
        tool,
        payload,
        store=request.app.state.document_store,
        gateway=request.app.state.llm_gateway,
        user_id=user_id,
        profile_override=profile_override,
        profile_id=profile_id,
    )


@router.post("/summary")
async def generate_summary(payload: StudyRequest, request: Request) -> dict[str, Any]:
    return await _generate("summary", payload, request)


@router.post("/mcq")
async def generate_mcqs(payload: StudyRequest, request: Request) -> dict[str, Any]:
    return await _generate("mcq", payload, request)


@router.post("/flashcards")
async def generate_flashcards(
    payload: StudyRequest, request: Request
) -> dict[str, Any]:
    return await _generate("flashcards", payload, request)


@router.post("/plan")
async def generate_plan(payload: StudyRequest, request: Request) -> dict[str, Any]:
    return await _generate("plan", payload, request)
