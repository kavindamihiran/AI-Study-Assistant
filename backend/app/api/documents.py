from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.documents.extraction import DocumentExtractionError, SUPPORTED_EXTENSIONS
from app.documents.store import DocumentStore


router = APIRouter(prefix="/api/documents", tags=["documents"])


def _store(request: Request) -> DocumentStore:
    return request.app.state.document_store


@router.get("")
async def list_documents(
    request: Request, study_session_id: str | None = None
) -> dict:
    return {
        "documents": _store(request).list_documents(
            study_session_id=study_session_id
        )
    }


@router.get("/{document_id}")
async def get_document(document_id: str, request: Request) -> dict:
    document = _store(request).get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    study_session_id: str | None = Form(default=None),
) -> dict:
    filename = file.filename or "document"
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Use: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(content) > request.app.state.max_upload_bytes:
        raise HTTPException(status_code=413, detail="The uploaded file is too large")
    try:
        return await _store(request).ingest(
            filename=filename,
            content_type=file.content_type,
            content=content,
            study_session_id=study_session_id,
        )
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, request: Request) -> None:
    if not await _store(request).delete(document_id):
        raise HTTPException(status_code=404, detail="Document not found")


@router.post("/{document_id}/reindex")
async def reindex_document(document_id: str, request: Request) -> dict:
    document = await _store(request).reindex(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
