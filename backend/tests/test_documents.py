from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.database import (
    ChatSessionModel,
    ChunkEmbeddingModel,
    DocumentChunkModel,
    DocumentModel,
    ModelRunModel,
)
from app.documents.extraction import (
    DocumentExtractionError,
    chunk_sections,
    extract_sections,
)
from app.documents.store import DocumentStore
from app.llm.models import NormalizedLLMResponse, TokenUsage
from app.main import create_app


RUNTIME_DIR = Path(__file__).parent / ".runtime-data"


class FakeStudyGateway:
    active_profile_id = "test_profile"

    async def generate_text(self, messages, **kwargs) -> NormalizedLLMResponse:
        return NormalizedLLMResponse(
            text="## Key ideas\n- Normalization reduces update anomalies.",
            model_id="test-model",
            profile_id="test_profile",
            usage=TokenUsage(input_tokens=50, output_tokens=20, total_tokens=70),
            latency_ms=2.5,
        )

    async def generate_json(self, messages, **kwargs) -> NormalizedLLMResponse:
        prompt = messages[-1].content
        if "multiple-choice" in prompt:
            parsed = {
                "mcqs": [
                    {
                        "question": "What does normalization reduce?",
                        "options": [
                            "Update anomalies",
                            "Network latency",
                            "File size",
                        ],
                        "answer_index": 0,
                        "explanation": "This is stated in the supplied notes.",
                    }
                ]
            }
        else:
            parsed = {
                "flashcards": [
                    {
                        "front": "What does normalization reduce?",
                        "back": "Database update anomalies.",
                    }
                ]
            }
        return NormalizedLLMResponse(
            text="",
            parsed_json=parsed,
            model_id="test-model",
            profile_id="test_profile",
            usage=TokenUsage(input_tokens=50, output_tokens=20, total_tokens=70),
            latency_ms=2.5,
        )


class DocumentExtractionTests(unittest.TestCase):
    def test_extracts_and_chunks_text(self) -> None:
        sections = extract_sections(
            "notes.txt",
            b"Database indexes speed up reads. B-trees keep keys ordered.",
        )
        chunks = chunk_sections(sections, chunk_words=6, overlap_words=2)

        self.assertEqual(len(sections), 1)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("Database indexes", chunks[0]["text"])

    def test_rejects_empty_text(self) -> None:
        with self.assertRaises(DocumentExtractionError):
            extract_sections("empty.md", b"   \n\n")


class DocumentStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
        self.store = DocumentStore(RUNTIME_DIR)

    def tearDown(self) -> None:
        self.store.database.engine.dispose()
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)

    async def test_ingests_retrieves_and_deletes_document(self) -> None:
        document = await self.store.ingest(
            filename="database.txt",
            content_type="text/plain",
            content=(
                b"A B-tree index keeps database keys sorted and supports "
                b"logarithmic lookup performance."
            ),
        )

        self.assertEqual(document["status"], "indexed")
        self.assertEqual(len(self.store.list_documents()), 1)
        with self.store.database.session() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(DocumentModel)),
                1,
            )
            self.assertGreater(
                session.scalar(
                    select(func.count()).select_from(DocumentChunkModel)
                ),
                0,
            )
            self.assertGreater(
                session.scalar(
                    select(func.count()).select_from(ChunkEmbeddingModel)
                ),
                0,
            )
        results = await self.store.retrieve("How does a B-tree index work?")
        self.assertEqual(results[0]["document_id"], document["id"])
        self.assertGreater(results[0]["vector_score"], 0)
        self.assertTrue(await self.store.delete(document["id"]))
        self.assertEqual(self.store.list_documents(), [])

    async def test_builds_study_context_from_selected_document(self) -> None:
        document = await self.store.ingest(
            filename="database.txt",
            content_type="text/plain",
            content=(
                b"Normalization reduces update anomalies. "
                b"A primary key uniquely identifies each row."
            ),
        )

        chunks = await self.store.get_study_chunks(
            document_ids=[document["id"]],
            focus="normalization",
        )

        self.assertGreater(len(chunks), 0)
        self.assertTrue(
            all(chunk["document_id"] == document["id"] for chunk in chunks)
        )
        self.assertIn("Normalization", chunks[0]["text"])

    async def test_deletes_study_session_documents_and_chats(self) -> None:
        workspace = self.store.create_study_session("Databases")
        document = await self.store.ingest(
            filename="database.txt",
            content_type="text/plain",
            content=b"Normalization reduces update anomalies.",
            study_session_id=workspace["id"],
        )
        session_id = self.store.ensure_chat_session(
            session_id=None,
            query="Explain normalization",
            profile_id="test_profile",
            study_session_id=workspace["id"],
        )
        self.store.add_chat_message(
            session_id=session_id,
            role="user",
            content="Explain normalization",
        )
        self.store.record_model_run(
            session_id=session_id,
            profile_id="test_profile",
            latency_ms=1,
            input_tokens=1,
            output_tokens=1,
            status="success",
            error_message=None,
            retry_count=0,
        )

        self.assertEqual(len(self.store.list_documents(workspace["id"])), 1)
        self.assertTrue(await self.store.delete_study_session(workspace["id"]))
        self.assertFalse((self.store.uploads_dir / f"{document['id']}.txt").exists())
        with self.store.database.session() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(DocumentModel)),
                0,
            )
            self.assertEqual(
                session.scalar(select(func.count()).select_from(ChatSessionModel)),
                0,
            )
            self.assertEqual(
                session.scalar(select(func.count()).select_from(ModelRunModel)),
                0,
            )


class DocumentApiTests(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
        settings = Settings(data_dir=RUNTIME_DIR)
        self.app = create_app(settings)
        self.app.state.llm_gateway = FakeStudyGateway()
        self.anon = TestClient(self.app)
        self.client = TestClient(self.app)
        self.csrf = self._register(self.client, "learner@example.com")
        self.auth_headers = {"X-CSRF-Token": self.csrf}

    def tearDown(self) -> None:
        self.app.state.database.engine.dispose()
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)

    def _register(self, client: TestClient, email: str) -> str:
        response = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "correct horse battery staple",
                "display_name": email.split("@", 1)[0],
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["user"]["email"], email)
        return payload["csrf_token"]

    def test_requires_authentication_and_csrf(self) -> None:
        self.assertEqual(self.anon.get("/api/documents").status_code, 401)

        missing_csrf = self.client.post(
            "/api/study-sessions",
            json={"title": "No CSRF"},
        )
        self.assertEqual(missing_csrf.status_code, 403)

        created = self.client.post(
            "/api/study-sessions",
            json={"title": "Databases"},
            headers=self.auth_headers,
        )
        self.assertEqual(created.status_code, 201)

    def test_registration_is_rate_limited(self) -> None:
        client = TestClient(self.app)

        for index in range(9):
            response = client.post(
                "/api/auth/register",
                json={
                    "email": f"public-{index}@example.com",
                    "password": "correct horse battery staple",
                    "display_name": f"public-{index}",
                },
            )
            self.assertEqual(response.status_code, 201)

        blocked = client.post(
            "/api/auth/register",
            json={
                "email": "public-blocked@example.com",
                "password": "correct horse battery staple",
                "display_name": "blocked",
            },
        )
        self.assertEqual(blocked.status_code, 429)

    def test_users_cannot_access_each_others_material(self) -> None:
        other = TestClient(self.app)
        other_csrf = self._register(other, "other@example.com")
        other_headers = {"X-CSRF-Token": other_csrf}

        workspace = self.client.post(
            "/api/study-sessions",
            json={"title": "Private subject"},
            headers=self.auth_headers,
        ).json()
        uploaded = self.client.post(
            "/api/documents/upload",
            data={"study_session_id": workspace["id"]},
            files={
                "file": (
                    "lecture.txt",
                    b"Normalization reduces database update anomalies.",
                    "text/plain",
                )
            },
            headers=self.auth_headers,
        ).json()

        self.assertEqual(other.get("/api/documents").json()["documents"], [])
        self.assertEqual(
            other.get(f"/api/documents/{uploaded['id']}").status_code,
            404,
        )
        self.assertEqual(
            other.delete(
                f"/api/study-sessions/{workspace['id']}",
                headers=other_headers,
            ).status_code,
            404,
        )
        isolated = other.post(
            "/api/study/summary",
            json={"document_ids": [uploaded["id"]]},
            headers=other_headers,
        )
        self.assertEqual(isolated.status_code, 422)

    def test_upload_list_and_delete(self) -> None:
        response = self.client.post(
            "/api/documents/upload",
            files={
                "file": (
                    "lecture.txt",
                    b"Normalization reduces database update anomalies.",
                    "text/plain",
                )
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 201)
        document = response.json()
        self.assertEqual(document["status"], "indexed")

        listed = self.client.get("/api/documents").json()["documents"]
        self.assertEqual(listed[0]["id"], document["id"])

        reindexed = self.client.post(
            f"/api/documents/{document['id']}/reindex",
            headers=self.auth_headers,
        )
        self.assertEqual(reindexed.status_code, 200)
        self.assertEqual(reindexed.json()["status"], "indexed")

        chat = self.client.post(
            "/api/chat",
            json={"query": "quantum mechanics", "document_ids": [document["id"]]},
            headers=self.auth_headers,
        )
        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["citations"], [])
        self.assertNotIn("profile_id", chat.json())
        self.assertNotIn("model_id", chat.json())
        session_id = chat.json()["session_id"]
        saved_session = self.client.get(f"/api/chat/sessions/{session_id}")
        self.assertEqual(saved_session.status_code, 200)
        self.assertEqual(len(saved_session.json()["messages"]), 2)
        deleted_session = self.client.delete(
            f"/api/chat/sessions/{session_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(deleted_session.status_code, 204)

        deleted = self.client.delete(
            f"/api/documents/{document['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(deleted.status_code, 204)

    def test_generates_grounded_study_material(self) -> None:
        uploaded = self.client.post(
            "/api/documents/upload",
            files={
                "file": (
                    "lecture.txt",
                    b"Normalization reduces database update anomalies.",
                    "text/plain",
                )
            },
            headers=self.auth_headers,
        ).json()

        summary = self.client.post(
            "/api/study/summary",
            json={"document_ids": [uploaded["id"]]},
            headers=self.auth_headers,
        )
        self.assertEqual(summary.status_code, 200)
        self.assertIn("Normalization", summary.json()["text"])
        self.assertEqual(summary.json()["citations"][0]["document_id"], uploaded["id"])

        mcqs = self.client.post(
            "/api/study/mcq",
            json={
                "document_ids": [uploaded["id"]],
                "topic": "normalization",
                "count": 1,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(mcqs.status_code, 200)
        item = mcqs.json()["data"]["items"][0]
        self.assertEqual(item["answer_index"], 0)
        self.assertEqual(item["options"][0], "Update anomalies")

        flashcards = self.client.post(
            "/api/study/flashcards",
            json={"document_ids": [uploaded["id"]], "count": 1},
            headers=self.auth_headers,
        )
        self.assertEqual(flashcards.status_code, 200)
        self.assertIn("normalization", flashcards.json()["data"]["items"][0]["front"].lower())

    def test_delete_study_session_removes_scoped_material(self) -> None:
        workspace = self.client.post(
            "/api/study-sessions",
            json={"title": "Databases"},
            headers=self.auth_headers,
        ).json()
        uploaded = self.client.post(
            "/api/documents/upload",
            data={"study_session_id": workspace["id"]},
            files={
                "file": (
                    "lecture.txt",
                    b"Normalization reduces database update anomalies.",
                    "text/plain",
                )
            },
            headers=self.auth_headers,
        ).json()
        chat = self.client.post(
            "/api/chat",
            json={
                "query": "What does normalization reduce?",
                "document_ids": [uploaded["id"]],
                "study_session_id": workspace["id"],
            },
            headers=self.auth_headers,
        )
        self.assertEqual(chat.status_code, 200)
        self.assertEqual(
            len(
                self.client.get(
                    f"/api/documents?study_session_id={workspace['id']}"
                ).json()["documents"]
            ),
            1,
        )

        deleted = self.client.delete(
            f"/api/study-sessions/{workspace['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(
            self.client.get(f"/api/study-sessions/{workspace['id']}").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/documents?study_session_id={workspace['id']}"
            ).json()["documents"],
            [],
        )
        self.assertEqual(
            self.client.get(
                f"/api/chat/sessions?study_session_id={workspace['id']}"
            ).json()["sessions"],
            [],
        )
