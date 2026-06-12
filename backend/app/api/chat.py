from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.documents.store import DocumentStore
from app.auth import current_auth, require_authenticated_request
from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage


router = APIRouter(
    prefix="/api/chat",
    tags=["chat"],
    dependencies=[Depends(require_authenticated_request)],
)
CHAT_PROFILE_ID = "study_ai_default"


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    document_ids: list[str] | None = None
    session_id: str | None = None
    study_session_id: str | None = None


@router.post("")
async def chat(payload: ChatRequest, request: Request) -> dict:
    store: DocumentStore = request.app.state.document_store
    gateway: LLMGateway = request.app.state.llm_gateway
    user_id = current_auth(request).user_id
    profile_id = CHAT_PROFILE_ID
    try:
        session_id = store.ensure_chat_session(
            session_id=payload.session_id,
            query=payload.query,
            profile_id=profile_id,
            study_session_id=payload.study_session_id,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    store.add_chat_message(
        session_id=session_id,
        role="user",
        content=payload.query,
        profile_id=profile_id,
        user_id=user_id,
    )
    chunks = await store.retrieve(
        payload.query,
        document_ids=payload.document_ids,
        limit=5,
        user_id=user_id,
    )
    if not chunks:
        answer = "I could not find this in your uploaded notes."
        store.add_chat_message(
            session_id=session_id,
            role="assistant",
            content=answer,
            citations=[],
            profile_id=profile_id,
            user_id=user_id,
        )
        return {
            "session_id": session_id,
            "answer_text": answer,
            "citations": [],
            "latency_ms": 0,
        }

    context_parts = []
    for index, chunk in enumerate(chunks, start=1):
        page = (
            f", page {chunk['page_number']}"
            if chunk.get("page_number") is not None
            else ""
        )
        context_parts.append(
            f"[Source {index}: {chunk['filename']}{page}]\n{chunk['text']}"
        )
    context_text = "\n\n".join(context_parts)
    prompt = (
        "Answer the student's question using only the supplied notes. "
        "If the notes do not contain the answer, say so. Be clear and concise. "
        "Do not invent sources.\n\n"
        f"QUESTION:\n{payload.query}\n\n"
        f"NOTES:\n{context_text}"
    )
    result = await gateway.generate_text(
        [
            ChatMessage(
                "system",
                "You are a study assistant that answers only from retrieved notes.",
            ),
            ChatMessage("user", prompt),
        ],
        profile_id=profile_id,
    )
    store.record_model_run(
        session_id=session_id,
        profile_id=result.profile_id or profile_id,
        latency_ms=result.latency_ms,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        status="success" if result.ok else "error",
        error_message=result.error_message,
        retry_count=result.retry_count,
        user_id=user_id,
    )
    if not result.ok:
        raise HTTPException(
            status_code=502,
            detail="The AI assistant is temporarily unavailable. Please try again.",
        )

    citations = [
        {
            "document_id": chunk["document_id"],
            "filename": chunk["filename"],
            "page_number": chunk.get("page_number"),
            "chunk_id": chunk["id"],
            "quoted_snippet": chunk["text"][:240],
            "relevance_score": chunk["relevance_score"],
        }
        for chunk in chunks
    ]
    store.add_chat_message(
        session_id=session_id,
        role="assistant",
        content=result.text,
        citations=citations,
        profile_id=result.profile_id,
        user_id=user_id,
    )
    return {
        "session_id": session_id,
        "answer_text": result.text,
        "citations": citations,
        "latency_ms": result.latency_ms,
    }


@router.get("/sessions")
async def list_chat_sessions(
    request: Request, study_session_id: str | None = None
) -> dict:
    store: DocumentStore = request.app.state.document_store
    return {
        "sessions": store.list_chat_sessions(
            study_session_id, user_id=current_auth(request).user_id
        )
    }


@router.get("/sessions/{session_id}")
async def get_chat_session(session_id: str, request: Request) -> dict:
    store: DocumentStore = request.app.state.document_store
    chat_session = store.get_chat_session(
        session_id, user_id=current_auth(request).user_id
    )
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return chat_session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_chat_session(session_id: str, request: Request) -> None:
    store: DocumentStore = request.app.state.document_store
    if not store.delete_chat_session(
        session_id, user_id=current_auth(request).user_id
    ):
        raise HTTPException(status_code=404, detail="Chat session not found")
