from __future__ import annotations

import base64
import hashlib
import shutil
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.models import NormalizedLLMResponse, TokenUsage
from app.main import create_app


RUNTIME_DIR = Path(__file__).parent / ".runtime-mcp"
PASSWORD = "correct horse battery staple"
REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"


class FakeMCPGateway:
    active_profile_id = "test_profile"

    async def generate_text(self, messages, **kwargs) -> NormalizedLLMResponse:
        return NormalizedLLMResponse(
            text="B-tree indexes keep keys sorted.",
            model_id="test-model",
            profile_id="test_profile",
            usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            latency_ms=1.0,
        )

    async def generate_json(self, messages, **kwargs) -> NormalizedLLMResponse:
        return NormalizedLLMResponse(
            text="",
            parsed_json={"items": [{"front": "Index?", "back": "Sorted keys."}]},
            model_id="test-model",
            profile_id="test_profile",
            usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            latency_ms=1.0,
        )


def _pkce() -> tuple[str, str]:
    verifier = "a" * 64
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


class MCPServerTests(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
        self.app = create_app(Settings(data_dir=RUNTIME_DIR, mcp_signing_secret="test"))
        self.app.state.llm_gateway = FakeMCPGateway()
        self.client = TestClient(self.app)
        self.csrf = self._register("learner@example.com")

    def tearDown(self) -> None:
        self.app.state.database.engine.dispose()
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)

    # ----- helpers -------------------------------------------------------

    def _register(self, email: str) -> str:
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "display_name": email.split("@", 1)[0],
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["csrf_token"]

    def _register_client(self) -> str:
        response = self.client.post(
            "/oauth/register",
            json={
                "client_name": "Claude",
                "redirect_uris": [REDIRECT_URI],
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["client_id"]

    def _authorize(self, client_id: str, challenge: str) -> str:
        """Run the browser half of the flow and return the authorization code."""
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        page = self.client.get("/oauth/authorize", params=params)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Allow access", page.text)
        ticket = page.text.split('name="login_ticket" value="')[1].split('"')[0]

        approved = self.client.post(
            "/oauth/authorize",
            data={**params, "login_ticket": ticket, "action": "approve"},
            follow_redirects=False,
        )
        self.assertEqual(approved.status_code, 302)
        location = urlparse(approved.headers["location"])
        query = parse_qs(location.query)
        self.assertEqual(query["state"], ["xyz"])
        return query["code"][0]

    def _connect(self) -> str:
        """Complete the whole OAuth dance and return an access token."""
        verifier, challenge = _pkce()
        client_id = self._register_client()
        code = self._authorize(client_id, challenge)
        response = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def _rpc(self, method: str, params: dict | None = None, *, token: str) -> dict:
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _upload(self, filename: str, body: bytes) -> str:
        response = self.client.post(
            "/api/documents/upload",
            files={"file": (filename, body, "text/plain")},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    # ----- discovery ------------------------------------------------------

    def test_publishes_discovery_metadata(self) -> None:
        resource = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(resource.status_code, 200)
        self.assertTrue(resource.json()["resource"].endswith("/mcp"))

        server = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(server.status_code, 200)
        metadata = server.json()
        self.assertEqual(metadata["code_challenge_methods_supported"], ["S256"])
        self.assertTrue(metadata["registration_endpoint"].endswith("/oauth/register"))

    def test_rejects_unauthenticated_calls_with_a_challenge(self) -> None:
        response = self.client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(
            "resource_metadata=", response.headers["WWW-Authenticate"]
        )

    def test_registration_rejects_an_insecure_redirect_uri(self) -> None:
        response = self.client.post(
            "/oauth/register",
            json={"client_name": "Bad", "redirect_uris": ["http://evil.test/cb"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_redirect_uri")

    # ----- OAuth ----------------------------------------------------------

    def test_authorization_code_flow_issues_a_usable_token(self) -> None:
        token = self._connect()
        payload = self._rpc("initialize", {"protocolVersion": "2025-06-18"}, token=token)
        self.assertEqual(payload["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(payload["result"]["serverInfo"]["name"], "studyos")

    def test_token_exchange_requires_the_matching_verifier(self) -> None:
        _, challenge = _pkce()
        client_id = self._register_client()
        code = self._authorize(client_id, challenge)
        response = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": "b" * 64,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_a_failed_verifier_burns_the_code(self) -> None:
        """One wrong guess is all a stolen authorization code gets."""
        verifier, challenge = _pkce()
        client_id = self._register_client()
        code = self._authorize(client_id, challenge)
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
        }
        guess = self.client.post(
            "/oauth/token", data={**body, "code_verifier": "b" * 64}
        )
        self.assertEqual(guess.status_code, 400)
        retry = self.client.post(
            "/oauth/token", data={**body, "code_verifier": verifier}
        )
        self.assertEqual(retry.status_code, 400)
        self.assertEqual(retry.json()["error"], "invalid_grant")

    def test_authorization_code_is_single_use(self) -> None:
        verifier, challenge = _pkce()
        client_id = self._register_client()
        code = self._authorize(client_id, challenge)
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }
        self.assertEqual(self.client.post("/oauth/token", data=body).status_code, 200)
        replay = self.client.post("/oauth/token", data=body)
        self.assertEqual(replay.status_code, 400)

    def test_refresh_rotates_the_grant(self) -> None:
        verifier, challenge = _pkce()
        client_id = self._register_client()
        code = self._authorize(client_id, challenge)
        first = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            },
        ).json()
        refreshed = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": first["refresh_token"],
                "client_id": client_id,
            },
        )
        self.assertEqual(refreshed.status_code, 200)
        second = refreshed.json()
        self.assertNotEqual(second["access_token"], first["access_token"])

        # The rotated-away tokens no longer work.
        replay = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": first["refresh_token"],
                "client_id": client_id,
            },
        )
        self.assertEqual(replay.status_code, 400)
        stale = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": f"Bearer {first['access_token']}"},
        )
        self.assertEqual(stale.status_code, 401)

    def test_declining_consent_redirects_with_an_error(self) -> None:
        _, challenge = _pkce()
        client_id = self._register_client()
        response = self.client.post(
            "/oauth/authorize",
            data={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
                "state": "xyz",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "action": "deny",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response.headers["location"]).query)
        self.assertEqual(query["error"], ["access_denied"])

    def test_authorize_rejects_an_unregistered_redirect_uri(self) -> None:
        _, challenge = _pkce()
        client_id = self._register_client()
        response = self.client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "https://evil.test/callback",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_authorize_requires_pkce(self) -> None:
        client_id = self._register_client()
        response = self.client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response.headers["location"]).query)
        self.assertEqual(query["error"], ["invalid_request"])

    def test_revocation_invalidates_the_access_token(self) -> None:
        token = self._connect()
        self.assertEqual(
            self.client.post("/oauth/revoke", data={"token": token}).status_code, 200
        )
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)

    def test_connections_are_listed_and_revocable_from_the_web_app(self) -> None:
        token = self._connect()
        listed = self.client.get("/api/mcp/connections")
        self.assertEqual(listed.status_code, 200)
        connections = listed.json()["connections"]
        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0]["client_name"], "Claude")
        self.assertIsNone(connections[0]["last_used_at"])

        # Using the connection stamps the access token; the listing reports the
        # latest use across the whole grant.
        self._rpc("ping", token=token)
        used = self.client.get("/api/mcp/connections").json()["connections"][0]
        self.assertIsNotNone(used["last_used_at"])

        deleted = self.client.delete(
            f"/api/mcp/connections/{connections[0]['grant_id']}",
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(deleted.status_code, 204)
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)

    # ----- protocol and tools ---------------------------------------------

    def test_lists_tools_and_ignores_notifications(self) -> None:
        token = self._connect()
        payload = self._rpc("tools/list", token=token)
        names = {tool["name"] for tool in payload["result"]["tools"]}
        self.assertIn("search_notes", names)
        self.assertIn("ask_notes", names)
        self.assertIn("list_documents", names)

        notification = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(notification.status_code, 202)

    def test_unknown_method_returns_a_jsonrpc_error(self) -> None:
        token = self._connect()
        payload = self._rpc("does/not/exist", token=token)
        self.assertEqual(payload["error"]["code"], -32601)

    def test_tool_failures_come_back_as_tool_errors(self) -> None:
        token = self._connect()
        payload = self._rpc(
            "tools/call",
            {"name": "get_document", "arguments": {"document_id": "missing"}},
            token=token,
        )
        self.assertTrue(payload["result"]["isError"])
        self.assertIn("not found", payload["result"]["content"][0]["text"].lower())

    def test_tools_reach_the_students_own_documents(self) -> None:
        token = self._connect()
        document_id = self._upload(
            "indexes.txt",
            b"A B-tree index keeps database keys sorted for fast lookups.",
        )

        listed = self._rpc(
            "tools/call", {"name": "list_documents", "arguments": {}}, token=token
        )
        self.assertIn(document_id, listed["result"]["content"][0]["text"])

        found = self._rpc(
            "tools/call",
            {"name": "search_notes", "arguments": {"query": "B-tree index"}},
            token=token,
        )
        self.assertIn("B-tree", found["result"]["content"][0]["text"])

        answered = self._rpc(
            "tools/call",
            {"name": "ask_notes", "arguments": {"question": "What is a B-tree index?"}},
            token=token,
        )
        self.assertFalse(answered["result"]["isError"])
        self.assertIn("B-tree", answered["result"]["content"][0]["text"])

    def test_add_note_indexes_new_content(self) -> None:
        token = self._connect()
        created = self._rpc(
            "tools/call",
            {
                "name": "add_note",
                "arguments": {
                    "title": "Transactions",
                    "text": "ACID transactions guarantee atomicity and durability.",
                },
            },
            token=token,
        )
        self.assertIn("indexed", created["result"]["content"][0]["text"])
        documents = self.client.get("/api/documents").json()["documents"]
        self.assertEqual(
            [document["filename"] for document in documents], ["Transactions.md"]
        )

    def test_a_token_cannot_reach_another_account(self) -> None:
        token = self._connect()
        self._upload("mine.txt", b"My own private notes about indexes.")

        other = TestClient(self.app)
        registration = other.post(
            "/api/auth/register",
            json={
                "email": "other@example.com",
                "password": PASSWORD,
                "display_name": "other",
            },
        )
        self.assertEqual(registration.status_code, 201)
        uploaded = other.post(
            "/api/documents/upload",
            files={
                "file": ("theirs.txt", b"Their private notes about indexes.", "text/plain")
            },
            headers={"X-CSRF-Token": registration.json()["csrf_token"]},
        )
        self.assertEqual(uploaded.status_code, 201)

        listed = self._rpc(
            "tools/call", {"name": "list_documents", "arguments": {}}, token=token
        )
        text = listed["result"]["content"][0]["text"]
        self.assertIn("mine.txt", text)
        self.assertNotIn("theirs.txt", text)

        searched = self._rpc(
            "tools/call",
            {"name": "search_notes", "arguments": {"query": "private notes about indexes"}},
            token=token,
        )
        self.assertNotIn("Their private", searched["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
