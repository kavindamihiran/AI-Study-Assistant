from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from sqlalchemy import delete, select

from app.database import ChunkEmbeddingModel, Database


@dataclass(frozen=True, slots=True)
class VectorMatch:
    chunk_id: str
    score: float


class VectorStore(Protocol):
    provider_name: str

    def upsert(
        self,
        records: Sequence[dict[str, Any]],
        vectors: Sequence[list[float]],
        *,
        embedding_model: str,
    ) -> None: ...

    def query(
        self,
        vector: list[float],
        *,
        document_ids: list[str] | None,
        limit: int,
    ) -> list[VectorMatch]: ...

    def delete_document(self, document_id: str) -> None: ...

    def health(self) -> bool: ...


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


class LocalSQLVectorStore:
    provider_name = "local_sql"

    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(
        self,
        records: Sequence[dict[str, Any]],
        vectors: Sequence[list[float]],
        *,
        embedding_model: str,
    ) -> None:
        if len(records) != len(vectors):
            raise ValueError("Records and vectors must have the same length")
        with self.database.session() as session:
            for record, vector in zip(records, vectors):
                session.merge(
                    ChunkEmbeddingModel(
                        chunk_id=record["id"],
                        document_id=record["document_id"],
                        embedding_json=json.dumps(vector, separators=(",", ":")),
                        dimension=len(vector),
                        embedding_model=embedding_model,
                    )
                )

    def query(
        self,
        vector: list[float],
        *,
        document_ids: list[str] | None,
        limit: int,
    ) -> list[VectorMatch]:
        statement = select(ChunkEmbeddingModel)
        if document_ids:
            statement = statement.where(
                ChunkEmbeddingModel.document_id.in_(document_ids)
            )
        with self.database.session() as session:
            embeddings = list(session.scalars(statement))
        matches = [
            VectorMatch(
                chunk_id=embedding.chunk_id,
                score=_cosine(vector, json.loads(embedding.embedding_json)),
            )
            for embedding in embeddings
        ]
        matches.sort(key=lambda match: match.score, reverse=True)
        return [match for match in matches if match.score > 0][:limit]

    def delete_document(self, document_id: str) -> None:
        with self.database.session() as session:
            session.execute(
                delete(ChunkEmbeddingModel).where(
                    ChunkEmbeddingModel.document_id == document_id
                )
            )

    def health(self) -> bool:
        return self.database.health()


class PineconeVectorStore:
    provider_name = "pinecone"

    def __init__(
        self,
        *,
        api_key: str,
        index_host: str,
        namespace: str,
    ) -> None:
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise RuntimeError(
                "Install the backend with the pinecone extra: pip install -e '.[pinecone]'"
            ) from exc
        self.namespace = namespace
        self.index = Pinecone(api_key=api_key).Index(host=index_host)

    def upsert(
        self,
        records: Sequence[dict[str, Any]],
        vectors: Sequence[list[float]],
        *,
        embedding_model: str,
    ) -> None:
        payload = [
            {
                "id": record["id"],
                "values": vector,
                "metadata": {
                    "document_id": record["document_id"],
                    "filename": record["filename"],
                    "page_number": record.get("page_number") or 0,
                    "chunk_index": record["chunk_index"],
                    "embedding_model": embedding_model,
                },
            }
            for record, vector in zip(records, vectors)
        ]
        for start in range(0, len(payload), 100):
            self.index.upsert(
                vectors=payload[start : start + 100],
                namespace=self.namespace,
            )

    def query(
        self,
        vector: list[float],
        *,
        document_ids: list[str] | None,
        limit: int,
    ) -> list[VectorMatch]:
        metadata_filter = (
            {"document_id": {"$in": document_ids}} if document_ids else None
        )
        response = self.index.query(
            namespace=self.namespace,
            vector=vector,
            top_k=limit,
            include_metadata=True,
            include_values=False,
            filter=metadata_filter,
        )
        matches = getattr(response, "matches", None) or response.get("matches", [])
        return [
            VectorMatch(
                chunk_id=getattr(match, "id", None) or match["id"],
                score=float(getattr(match, "score", None) or match["score"]),
            )
            for match in matches
        ]

    def delete_document(self, document_id: str) -> None:
        self.index.delete(
            namespace=self.namespace,
            filter={"document_id": {"$eq": document_id}},
        )

    def health(self) -> bool:
        try:
            self.index.describe_index_stats()
            return True
        except Exception:
            return False

