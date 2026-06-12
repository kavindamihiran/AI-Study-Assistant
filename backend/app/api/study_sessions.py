from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.documents.store import DocumentStore


router = APIRouter(prefix="/api/study-sessions", tags=["study-sessions"])


class StudySessionCreateRequest(BaseModel):
    title: str = Field(default="New study session", max_length=120)


def _store(request: Request) -> DocumentStore:
    return request.app.state.document_store


@router.get("")
async def list_study_sessions(request: Request) -> dict:
    return {"sessions": _store(request).list_study_sessions()}


@router.post("", status_code=201)
async def create_study_session(
    payload: StudySessionCreateRequest, request: Request
) -> dict:
    return _store(request).create_study_session(payload.title)


@router.get("/{study_session_id}")
async def get_study_session(study_session_id: str, request: Request) -> dict:
    session = _store(request).get_study_session(study_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Study session not found")
    return session


@router.delete("/{study_session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_study_session(study_session_id: str, request: Request) -> None:
    if not await _store(request).delete_study_session(study_session_id):
        raise HTTPException(status_code=404, detail="Study session not found")
