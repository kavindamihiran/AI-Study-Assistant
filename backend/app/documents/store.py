from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import joinedload

from app.database import (
    ChatMessageModel,
    ChatSessionModel,
    Database,
    DocumentChunkModel,
    DocumentModel,
    ModelRunModel,
    StudySessionModel,
)
from app.rag.embeddings import EmbeddingProvider, HashingEmbeddingProvider
from app.rag.vector_store import LocalSQLVectorStore, VectorMatch, VectorStore

from .extraction import chunk_sections, extract_sections


_WORD = re.compile(r"[a-z0-9]{2,}")
_STOP_WORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "does",
    "for",
    "from",
    "how",
    "into",
    "its",
    "that",
    "the",
    "this",
    "was",
    "what",
    "when",
    "where",
    "which",
    "with",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _WORD.findall(text.lower())
        if token not in _STOP_WORDS
    }


def _document_dict(document: DocumentModel) -> dict[str, Any]:
    return {
        "id": document.id,
        "filename": document.filename,
        "file_type": document.file_type,
        "content_type": document.content_type,
        "file_size": document.file_size,
        "title": document.title,
        "study_session_id": document.study_session_id,
        "status": document.status,
        "chunk_count": document.chunk_count,
        "character_count": document.character_count,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
        "error": document.error,
    }


class DocumentStore:
    def __init__(
        self,
        data_dir: str | Path,
        *,
        database: Database | None = None,
        embedder: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.uploads_dir = self.data_dir / "uploads"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.database = database or Database(
            Database.sqlite_url(self.data_dir / "study_assistant.db")
        )
        self.database.initialize()
        self.embedder = embedder or HashingEmbeddingProvider()
        self.vector_store = vector_store or LocalSQLVectorStore(self.database)
        self._migrate_legacy_json()

    @property
    def status(self) -> dict[str, Any]:
        return {
            "database": "connected" if self.database.health() else "unavailable",
            "database_backend": self.database.url.split(":", 1)[0],
            "vector_store": self.vector_store.provider_name,
            "vector_store_ready": self.vector_store.health(),
            "embedding_model": self.embedder.model_id,
            "embedding_dimension": self.embedder.dimension,
        }

    def _migrate_legacy_json(self) -> None:
        legacy_index = self.data_dir / "documents.json"
        if not legacy_index.exists():
            return
        with self.database.session() as session:
            existing = session.scalar(select(DocumentModel.id).limit(1))
        if existing:
            return
        try:
            documents = json.loads(legacy_index.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not documents:
            return

        chunks_dir = self.data_dir / "chunks"
        with self.database.session() as session:
            for item in documents:
                document_id = item["id"]
                extension = f".{item.get('file_type', '')}" if item.get("file_type") else ""
                stored_path = self.uploads_dir / f"{document_id}{extension}"
                document = DocumentModel(
                    id=document_id,
                    filename=item["filename"],
                    file_type=item.get("file_type", ""),
                    content_type=item.get("content_type"),
                    file_size=item.get("file_size", 0),
                    title=item.get("title") or Path(item["filename"]).stem,
                    study_session_id=None,
                    status="processing",
                    stored_path=str(stored_path),
                    chunk_count=item.get("chunk_count", 0),
                    character_count=item.get("character_count", 0),
                    error=None,
                    created_at=datetime.fromisoformat(item["created_at"]),
                )
                session.add(document)
                chunk_path = chunks_dir / f"{document_id}.json"
                try:
                    chunks = json.loads(chunk_path.read_text(encoding="utf-8"))
                except (FileNotFoundError, json.JSONDecodeError):
                    chunks = []
                for chunk in chunks:
                    session.add(
                        DocumentChunkModel(
                            id=chunk["id"],
                            document_id=document_id,
                            chunk_index=chunk["chunk_index"],
                            chunk_text=chunk["text"],
                            page_number=chunk.get("page_number"),
                            word_count=chunk.get("word_count", len(chunk["text"].split())),
                        )
                    )
        legacy_index.rename(legacy_index.with_suffix(".json.migrated"))

    def create_study_session(
        self, title: str | None = None, *, user_id: str | None = None
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        session_title = (title or "New study session").strip()[:120]
        with self.database.session() as session:
            item = StudySessionModel(
                id=session_id, user_id=user_id, title=session_title
            )
            session.add(item)
        session_item = self.get_study_session(session_id, user_id=user_id)
        if session_item is None:
            raise RuntimeError("Study session disappeared after creation")
        return session_item

    def list_study_sessions(
        self, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        statement = select(StudySessionModel)
        if user_id is not None:
            statement = statement.where(
                StudySessionModel.user_id == user_id
            )
        statement = statement.order_by(StudySessionModel.updated_at.desc())
        with self.database.session() as session:
            items = list(session.scalars(statement))
        return [
            {
                "id": item.id,
                "title": item.title,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in items
        ]

    def get_study_session(
        self, study_session_id: str, *, user_id: str | None = None
    ) -> dict[str, Any] | None:
        with self.database.session() as session:
            statement = select(StudySessionModel).where(
                StudySessionModel.id == study_session_id
            )
            if user_id is not None:
                statement = statement.where(
                    StudySessionModel.user_id == user_id
                )
            item = session.scalar(statement)
            if item is None:
                return None
            return {
                "id": item.id,
                "title": item.title,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }

    def _is_default_study_session(
        self, study_session_id: str, *, user_id: str | None = None
    ) -> bool:
        with self.database.session() as session:
            general_statement = select(StudySessionModel.id).where(
                StudySessionModel.title == "General study session"
            )
            oldest_statement = select(StudySessionModel.id)
            if user_id is not None:
                general_statement = general_statement.where(
                    StudySessionModel.user_id == user_id
                )
                oldest_statement = oldest_statement.where(
                    StudySessionModel.user_id == user_id
                )
            general = session.scalar(
                general_statement.order_by(
                    StudySessionModel.created_at.asc()
                ).limit(1)
            )
            if general:
                return general == study_session_id
            oldest = session.scalar(
                oldest_statement.order_by(
                    StudySessionModel.created_at.asc()
                ).limit(1)
            )
            return oldest == study_session_id

    async def delete_study_session(
        self, study_session_id: str, *, user_id: str | None = None
    ) -> bool:
        include_unassigned = self._is_default_study_session(
            study_session_id, user_id=user_id
        )
        with self.database.session() as session:
            session_statement = select(StudySessionModel).where(
                StudySessionModel.id == study_session_id
            )
            if user_id is not None:
                session_statement = session_statement.where(
                    StudySessionModel.user_id == user_id
                )
            study_session = session.scalar(session_statement)
            if study_session is None:
                return False

            document_filter = DocumentModel.study_session_id == study_session_id
            chat_filter = ChatSessionModel.study_session_id == study_session_id
            if include_unassigned:
                document_filter = or_(
                    document_filter,
                    (
                        DocumentModel.study_session_id.is_(None)
                        if user_id is None
                        else (
                            DocumentModel.study_session_id.is_(None)
                            & (DocumentModel.user_id == user_id)
                        )
                    ),
                )
                chat_filter = or_(
                    chat_filter,
                    (
                        ChatSessionModel.study_session_id.is_(None)
                        if user_id is None
                        else (
                            ChatSessionModel.study_session_id.is_(None)
                            & (ChatSessionModel.user_id == user_id)
                        )
                    ),
                )
            if user_id is not None:
                document_filter = (
                    document_filter & (DocumentModel.user_id == user_id)
                )
                chat_filter = (
                    chat_filter & (ChatSessionModel.user_id == user_id)
                )

            documents = list(
                session.scalars(
                    select(DocumentModel).where(document_filter)
                )
            )
            chat_session_ids = list(
                session.scalars(
                    select(ChatSessionModel.id).where(chat_filter)
                )
            )
            document_ids = [document.id for document in documents]
            stored_paths = [document.stored_path for document in documents]

        for document_id in document_ids:
            await asyncio.to_thread(self.vector_store.delete_document, document_id)

        with self.database.session() as session:
            if chat_session_ids:
                session.execute(
                    delete(ModelRunModel).where(
                        ModelRunModel.session_id.in_(chat_session_ids)
                    )
                )
                session.execute(
                    delete(ChatSessionModel).where(
                        ChatSessionModel.id.in_(chat_session_ids)
                    )
                )
            if document_ids:
                session.execute(
                    delete(DocumentModel).where(DocumentModel.id.in_(document_ids))
                )
            session.execute(
                delete(StudySessionModel).where(
                    StudySessionModel.id == study_session_id,
                    *(
                        [StudySessionModel.user_id == user_id]
                        if user_id is not None
                        else []
                    ),
                )
            )

        for stored_path in stored_paths:
            await asyncio.to_thread(Path(stored_path).unlink, missing_ok=True)
        return True

    def list_documents(
        self,
        study_session_id: str | None = None,
        *,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.database.session() as session:
            statement = select(DocumentModel).order_by(
                DocumentModel.created_at.desc()
            )
            if user_id is not None:
                statement = statement.where(DocumentModel.user_id == user_id)
            if study_session_id:
                if self._is_default_study_session(
                    study_session_id, user_id=user_id
                ):
                    statement = statement.where(
                        or_(
                            DocumentModel.study_session_id == study_session_id,
                            DocumentModel.study_session_id.is_(None),
                        )
                    )
                else:
                    statement = statement.where(
                        DocumentModel.study_session_id == study_session_id
                    )
            documents = list(session.scalars(statement))
        return [_document_dict(document) for document in documents]

    def get_document(
        self, document_id: str, *, user_id: str | None = None
    ) -> dict[str, Any] | None:
        with self.database.session() as session:
            statement = select(DocumentModel).where(
                DocumentModel.id == document_id
            )
            if user_id is not None:
                statement = statement.where(DocumentModel.user_id == user_id)
            document = session.scalar(statement)
            return _document_dict(document) if document else None

    async def ingest(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
        study_session_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        document_id = uuid.uuid4().hex
        safe_name = Path(filename).name
        extension = Path(safe_name).suffix.lower()
        stored_path = self.uploads_dir / f"{document_id}{extension}"
        if study_session_id and self.get_study_session(
            study_session_id, user_id=user_id
        ) is None:
            raise ValueError("Study session not found")
        sections = await asyncio.to_thread(extract_sections, safe_name, content)
        chunks = chunk_sections(sections)
        character_count = sum(len(section.text) for section in sections)
        await asyncio.to_thread(stored_path.write_bytes, content)

        chunk_records = [
            {
                **chunk,
                "id": f"{document_id}:{chunk['chunk_index']}",
                "document_id": document_id,
                "filename": safe_name,
            }
            for chunk in chunks
        ]
        with self.database.session() as session:
            session.add(
                DocumentModel(
                    id=document_id,
                    user_id=user_id,
                    filename=safe_name,
                    file_type=extension.lstrip("."),
                    content_type=content_type,
                    file_size=len(content),
                    title=Path(safe_name).stem,
                    study_session_id=study_session_id,
                    status="processing",
                    stored_path=str(stored_path),
                    chunk_count=len(chunks),
                    character_count=character_count,
                )
            )
            session.add_all(
                [
                    DocumentChunkModel(
                        id=chunk["id"],
                        document_id=document_id,
                        chunk_index=chunk["chunk_index"],
                        chunk_text=chunk["text"],
                        page_number=chunk.get("page_number"),
                        word_count=chunk["word_count"],
                    )
                    for chunk in chunk_records
                ]
            )

        try:
            vectors = await self.embedder.embed_documents(
                [chunk["text"] for chunk in chunk_records]
            )
            await asyncio.to_thread(
                self.vector_store.upsert,
                chunk_records,
                vectors,
                embedding_model=self.embedder.model_id,
            )
            with self.database.session() as session:
                document = session.get(DocumentModel, document_id)
                if document:
                    document.status = "indexed"
                    document.error = None
                    document.updated_at = datetime.now(UTC)
        except Exception as exc:
            with self.database.session() as session:
                document = session.get(DocumentModel, document_id)
                if document:
                    document.status = "failed"
                    document.error = str(exc)
                    document.updated_at = datetime.now(UTC)
            raise

        document = self.get_document(document_id, user_id=user_id)
        if document is None:
            raise RuntimeError("Document disappeared after ingestion")
        return document

    async def delete(
        self, document_id: str, *, user_id: str | None = None
    ) -> bool:
        with self.database.session() as session:
            statement = select(DocumentModel).where(
                DocumentModel.id == document_id
            )
            if user_id is not None:
                statement = statement.where(DocumentModel.user_id == user_id)
            document = session.scalar(statement)
            if document is None:
                return False
            stored_path = document.stored_path
        await asyncio.to_thread(self.vector_store.delete_document, document_id)
        with self.database.session() as session:
            session.execute(
                delete(DocumentModel).where(
                    DocumentModel.id == document_id,
                    *(
                        [DocumentModel.user_id == user_id]
                        if user_id is not None
                        else []
                    ),
                )
            )
        await asyncio.to_thread(Path(stored_path).unlink, missing_ok=True)
        return True

    async def reindex(
        self, document_id: str, *, user_id: str | None = None
    ) -> dict[str, Any] | None:
        with self.database.session() as session:
            statement = select(DocumentModel).where(
                DocumentModel.id == document_id
            )
            if user_id is not None:
                statement = statement.where(DocumentModel.user_id == user_id)
            document = session.scalar(statement)
            if document is None:
                return None
            document.status = "processing"
            document.error = None
            chunks = list(
                session.scalars(
                    select(DocumentChunkModel)
                    .where(DocumentChunkModel.document_id == document_id)
                    .order_by(DocumentChunkModel.chunk_index.asc())
                )
            )
            chunk_records = [
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "filename": document.filename,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.chunk_text,
                    "page_number": chunk.page_number,
                }
                for chunk in chunks
            ]
        try:
            vectors = await self.embedder.embed_documents(
                [chunk["text"] for chunk in chunk_records]
            )
            await asyncio.to_thread(
                self.vector_store.upsert,
                chunk_records,
                vectors,
                embedding_model=self.embedder.model_id,
            )
            with self.database.session() as session:
                document = session.get(DocumentModel, document_id)
                if document:
                    document.status = "indexed"
                    document.error = None
                    document.updated_at = datetime.now(UTC)
        except Exception as exc:
            with self.database.session() as session:
                document = session.get(DocumentModel, document_id)
                if document:
                    document.status = "failed"
                    document.error = str(exc)
            raise
        return self.get_document(document_id, user_id=user_id)

    def _load_chunks(
        self,
        document_ids: list[str] | None = None,
        *,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        statement = (
            select(DocumentChunkModel)
            .options(joinedload(DocumentChunkModel.document))
            .join(DocumentModel)
            .where(DocumentModel.status == "indexed")
            .order_by(
                DocumentChunkModel.document_id.asc(),
                DocumentChunkModel.chunk_index.asc(),
            )
        )
        if document_ids:
            statement = statement.where(
                DocumentChunkModel.document_id.in_(document_ids)
            )
        if user_id is not None:
            statement = statement.where(DocumentModel.user_id == user_id)
        with self.database.session() as session:
            chunks = list(session.scalars(statement))
            return [
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "filename": chunk.document.filename,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.chunk_text,
                    "page_number": chunk.page_number,
                    "word_count": chunk.word_count,
                }
                for chunk in chunks
            ]

    def get_document_chunks(
        self, document_id: str, *, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Every indexed chunk of one document, in reading order."""
        return self._load_chunks([document_id], user_id=user_id)

    async def retrieve(
        self,
        query: str,
        *,
        document_ids: list[str] | None = None,
        limit: int = 5,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        chunks = await asyncio.to_thread(
            self._load_chunks, document_ids, user_id=user_id
        )
        if not chunks:
            return []
        owned_document_ids = list(
            dict.fromkeys(chunk["document_id"] for chunk in chunks)
        )
        query_vector = await self.embedder.embed_query(query)
        vector_matches = await asyncio.to_thread(
            self.vector_store.query,
            query_vector,
            document_ids=owned_document_ids,
            limit=max(limit * 4, 20),
        )
        chunks_by_id = {chunk["id"]: chunk for chunk in chunks}
        vector_scores = {
            match.chunk_id: max(0.0, match.score) for match in vector_matches
        }

        query_tokens = _tokens(query)
        query_lower = query.lower().strip()
        scored: list[tuple[float, dict[str, Any]]] = []
        candidate_ids = set(vector_scores)
        for chunk in chunks:
            chunk_tokens = _tokens(chunk["text"])
            overlap = query_tokens & chunk_tokens
            lexical = len(overlap) / max(len(query_tokens), 1)
            if query_lower and query_lower in chunk["text"].lower():
                lexical += 0.35
            if lexical > 0:
                candidate_ids.add(chunk["id"])
            chunk["_lexical_score"] = lexical

        for chunk_id in candidate_ids:
            chunk = chunks_by_id.get(chunk_id)
            if not chunk:
                continue
            vector_score = vector_scores.get(chunk_id, 0.0)
            lexical_score = chunk.pop("_lexical_score", 0.0)
            if vector_score < 0.08 and lexical_score <= 0:
                continue
            combined = (vector_score * 0.72) + (lexical_score * 0.28)
            scored.append(
                (
                    combined,
                    {
                        **chunk,
                        "relevance_score": round(combined, 4),
                        "vector_score": round(vector_score, 4),
                        "lexical_score": round(lexical_score, 4),
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:limit]]

    async def get_study_chunks(
        self,
        *,
        document_ids: list[str],
        focus: str | None = None,
        max_characters: int = 50000,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build broad, document-balanced context with optional focus weighting."""
        chunks = await asyncio.to_thread(
            self._load_chunks, document_ids, user_id=user_id
        )
        if not chunks:
            return []

        total_characters = sum(len(chunk["text"]) for chunk in chunks)
        if total_characters <= max_characters:
            return [
                {
                    **chunk,
                    "relevance_score": 1.0,
                }
                for chunk in chunks
            ]

        selected: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        used_characters = 0

        if focus and focus.strip():
            focused = await self.retrieve(
                focus.strip(),
                document_ids=document_ids,
                limit=min(12, len(chunks)),
                user_id=user_id,
            )
            focus_budget = max_characters // 3
            for chunk in focused:
                chunk_size = len(chunk["text"])
                if used_characters + chunk_size > focus_budget:
                    continue
                selected.append(chunk)
                selected_ids.add(chunk["id"])
                used_characters += chunk_size

        chunks_by_document: dict[str, list[dict[str, Any]]] = {}
        for chunk in chunks:
            if chunk["id"] not in selected_ids:
                chunks_by_document.setdefault(chunk["document_id"], []).append(chunk)

        remaining_budget = max_characters - used_characters
        document_count = max(len(chunks_by_document), 1)
        per_document_budget = max(1000, remaining_budget // document_count)

        for document_chunks in chunks_by_document.values():
            if not document_chunks:
                continue
            average_size = max(
                1,
                sum(len(chunk["text"]) for chunk in document_chunks)
                // len(document_chunks),
            )
            target_count = max(1, per_document_budget // average_size)
            target_count = min(target_count, len(document_chunks))
            if target_count == 1:
                indexes = [len(document_chunks) // 2]
            else:
                indexes = [
                    round(index * (len(document_chunks) - 1) / (target_count - 1))
                    for index in range(target_count)
                ]
            for index in indexes:
                chunk = document_chunks[index]
                if chunk["id"] in selected_ids:
                    continue
                chunk_size = len(chunk["text"])
                if used_characters + chunk_size > max_characters:
                    continue
                selected.append({**chunk, "relevance_score": 0.5})
                selected_ids.add(chunk["id"])
                used_characters += chunk_size

        if not selected:
            first = chunks[0]
            selected.append(
                {
                    **first,
                    "text": first["text"][:max_characters],
                    "relevance_score": 0.5,
                }
            )
        return selected

    def ensure_chat_session(
        self,
        *,
        session_id: str | None,
        query: str,
        profile_id: str | None,
        study_session_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        session_id = session_id or uuid.uuid4().hex
        with self.database.session() as session:
            if study_session_id:
                study_session_statement = select(
                    StudySessionModel.id
                ).where(StudySessionModel.id == study_session_id)
                if user_id is not None:
                    study_session_statement = (
                        study_session_statement.where(
                            StudySessionModel.user_id == user_id
                        )
                    )
                if session.scalar(study_session_statement) is None:
                    raise ValueError("Study session not found")
            chat_session = session.get(ChatSessionModel, session_id)
            if chat_session is None:
                session.add(
                    ChatSessionModel(
                        id=session_id,
                        user_id=user_id,
                        title=query[:80],
                        active_model_profile_id=profile_id,
                        study_session_id=study_session_id,
                    )
                )
            else:
                if user_id is not None and chat_session.user_id != user_id:
                    raise ValueError("Chat session not found")
                chat_session.updated_at = datetime.now(UTC)
                chat_session.active_model_profile_id = profile_id
                if study_session_id:
                    chat_session.study_session_id = study_session_id
        return session_id

    def add_chat_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        profile_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        with self.database.session() as session:
            chat_statement = select(ChatSessionModel.id).where(
                ChatSessionModel.id == session_id
            )
            if user_id is not None:
                chat_statement = chat_statement.where(
                    ChatSessionModel.user_id == user_id
                )
            if session.scalar(chat_statement) is None:
                raise ValueError("Chat session not found")
            session.add(
                ChatMessageModel(
                    id=uuid.uuid4().hex,
                    session_id=session_id,
                    role=role,
                    content=content,
                    citations_json=(
                        json.dumps(citations, ensure_ascii=True)
                        if citations is not None
                        else None
                    ),
                    model_profile_id=profile_id,
                )
            )

    def record_model_run(
        self,
        *,
        session_id: str | None,
        profile_id: str | None,
        latency_ms: float,
        input_tokens: int | None,
        output_tokens: int | None,
        status: str,
        error_message: str | None,
        retry_count: int,
        graph_node_name: str = "rag_answer",
        user_id: str | None = None,
    ) -> None:
        with self.database.session() as session:
            session.add(
                ModelRunModel(
                    id=uuid.uuid4().hex,
                    user_id=user_id,
                    session_id=session_id,
                    model_profile_id=profile_id,
                    graph_node_name=graph_node_name,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status=status,
                    error_message=error_message,
                    retry_count=retry_count,
                    used_fallback=retry_count > 0,
                )
            )

    def list_chat_sessions(
        self,
        study_session_id: str | None = None,
        *,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.database.session() as session:
            statement = select(ChatSessionModel).order_by(
                ChatSessionModel.updated_at.desc()
            )
            if user_id is not None:
                statement = statement.where(
                    ChatSessionModel.user_id == user_id
                )
            if study_session_id:
                if self._is_default_study_session(
                    study_session_id, user_id=user_id
                ):
                    statement = statement.where(
                        or_(
                            ChatSessionModel.study_session_id == study_session_id,
                            ChatSessionModel.study_session_id.is_(None),
                        )
                    )
                else:
                    statement = statement.where(
                        ChatSessionModel.study_session_id == study_session_id
                    )
            sessions = list(session.scalars(statement))
        return [
            {
                "id": item.id,
                "title": item.title,
                "active_model_profile_id": None,
                "study_session_id": item.study_session_id,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in sessions
        ]

    def get_chat_session(
        self, session_id: str, *, user_id: str | None = None
    ) -> dict[str, Any] | None:
        with self.database.session() as session:
            statement = select(ChatSessionModel).where(
                ChatSessionModel.id == session_id
            )
            if user_id is not None:
                statement = statement.where(
                    ChatSessionModel.user_id == user_id
                )
            chat_session = session.scalar(statement)
            if chat_session is None:
                return None
            messages = list(
                session.scalars(
                    select(ChatMessageModel)
                    .where(ChatMessageModel.session_id == session_id)
                    .order_by(ChatMessageModel.created_at.asc())
                )
            )
            return {
                "id": chat_session.id,
                "title": chat_session.title,
                "active_model_profile_id": None,
                "study_session_id": chat_session.study_session_id,
                "messages": [
                    {
                        "id": message.id,
                        "role": message.role,
                        "content": message.content,
                        "citations": (
                            json.loads(message.citations_json)
                            if message.citations_json
                            else []
                        ),
                        "model_profile_id": None,
                        "created_at": message.created_at.isoformat(),
                    }
                    for message in messages
                ],
            }

    def delete_chat_session(
        self, session_id: str, *, user_id: str | None = None
    ) -> bool:
        with self.database.session() as session:
            statement = select(ChatSessionModel).where(
                ChatSessionModel.id == session_id
            )
            if user_id is not None:
                statement = statement.where(
                    ChatSessionModel.user_id == user_id
                )
            chat_session = session.scalar(statement)
            if chat_session is None:
                return False
            session.delete(chat_session)
            session.execute(
                delete(ModelRunModel).where(ModelRunModel.session_id == session_id)
            )
        return True
