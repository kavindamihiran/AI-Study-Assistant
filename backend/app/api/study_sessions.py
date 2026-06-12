from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.documents.store import DocumentStore
from app.auth import current_auth, require_authenticated_request


router = APIRouter(
    prefix="/api/study-sessions",
    tags=["study-sessions"],
    dependencies=[Depends(require_authenticated_request)],
)


class StudySessionCreateRequest(BaseModel):
    title: str = Field(default="New study session", max_length=120)


def _store(request: Request) -> DocumentStore:
    return request.app.state.document_store


@router.get("")
async def list_study_sessions(request: Request) -> dict:
    return {
        "sessions": _store(request).list_study_sessions(
            current_auth(request).user_id
        )
    }


@router.post("", status_code=201)
async def create_study_session(
    payload: StudySessionCreateRequest, request: Request
) -> dict:
    return _store(request).create_study_session(
        payload.title, user_id=current_auth(request).user_id
    )


@router.get("/{study_session_id}")
async def get_study_session(study_session_id: str, request: Request) -> dict:
    session = _store(request).get_study_session(
        study_session_id, user_id=current_auth(request).user_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Study session not found")
    return session


@router.delete("/{study_session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_study_session(study_session_id: str, request: Request) -> None:
    if not await _store(request).delete_study_session(
        study_session_id, user_id=current_auth(request).user_id
    ):
        raise HTTPException(status_code=404, detail="Study session not found")
