# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

StudyOS: a Next.js frontend (static export) plus a FastAPI backend that answers questions from uploaded course documents through a custom RAG pipeline and a provider-agnostic LLM gateway. The two halves are separate deployables that only communicate over REST with cookie auth.

## Commands

The backend virtualenv lives at `backend/.venv` (`backend/.venv-api` is also accepted by the dev script). All commands below are Linux/macOS; the README documents PowerShell equivalents.

```bash
# Install backend (editable, with dev extras)
cd backend && ./.venv/bin/python -m pip install -e ".[dev]"

# Run both servers (Next.js :3000 + uvicorn :8000) — the normal dev entry point
cd frontend && npm run dev
# Frontend alone, when FastAPI is already running:
cd frontend && npm run dev:frontend

# Backend alone
cd backend && ./.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# Backend tests (26 tests, all should pass)
cd backend && ./.venv/bin/python -m pytest tests -q -p no:cacheprovider
# One file / one test
cd backend && ./.venv/bin/python -m pytest tests/test_gateway.py -q
cd backend && ./.venv/bin/python -m pytest tests/test_documents.py::DocumentStoreTests::test_ingests_retrieves_and_deletes_document -q

# Frontend "test" = a clean production static export must succeed
cd frontend && npm run build
```

There is no linter or formatter configured for either half.

API docs while the backend runs: `http://127.0.0.1:8000/docs`.

## Environment

Backend config is read only through `Settings.from_env()` (`backend/app/config.py`), which loads `.env` / `.env.local` from both the repo root and `backend/` with `os.environ.setdefault` — real process env always wins. Add new settings as a dataclass field plus an `os.getenv` line there; never read `os.getenv` from feature code.

Minimum to run: `AI_API_KEY`, `AI_BASE_URL`, `AI_DEFAULT_MODEL_ID` — or nothing at all, if every user brings their own key through Settings (see "Per-user models"). `SECRET_ENCRYPTION_KEY` encrypts those saved keys; without it a key file is generated under `DATA_DIR`. Without `DATABASE_URL` the app falls back to SQLite at `backend/data/study_assistant.db`. The frontend needs `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://127.0.0.1:8000`); it is baked in at build time because the app is statically exported.

## Backend architecture

`create_app()` in `backend/app/main.py` is the single composition root. It builds the model registry, gateway, database, auth service, embedder, vector store and document store, then hangs them off `app.state`. Routes pull collaborators from `request.app.state.*` rather than importing singletons — this is what lets tests swap in a `FakeStudyGateway` or a temp-directory `DocumentStore`. Adding a swappable dependency means wiring it here, not creating a module-level instance.

### Layers

- `app/api/` — FastAPI routers (`/api/auth`, `/api/documents`, `/api/chat`, `/api/study`, `/api/study-sessions`, `/api/settings/model`). Routers hold prompt construction and HTTP mapping only.
- `app/llm/` — the gateway (see below).
- `app/documents/store.py` — `DocumentStore`, the main data-access object: study sessions, documents, chunks, chat sessions/messages, model runs, plus retrieval. Nearly everything persistence-related goes through it.
- `app/rag/` — `EmbeddingProvider` (local feature-hashing or hosted) and `VectorStore` (SQL-backed or Pinecone), both duck-typed protocols selected by env.
- `app/security/` — `SecretBox`, stdlib-only authenticated encryption for secrets stored in the database.
- `app/database/` — SQLAlchemy 2 models and the `Database` wrapper (`session()` contextmanager commits on exit, rolls back on exception).

### Auth and per-user scoping (invariant)

Every router except `/api/auth/register|login` mounts `dependencies=[Depends(require_authenticated_request)]`, which validates the `HttpOnly` session cookie and — for non-GET/HEAD/OPTIONS — requires a matching `X-CSRF-Token` header. Handlers then read `current_auth(request).user_id` and pass `user_id=` down into every `DocumentStore` call, which filters the SQL by owner. **Any new query or store method must take and apply `user_id`**; dropping it silently leaks other accounts' data.

Session tokens are stored only as SHA-256 hashes; passwords use `scrypt`. Login and registration are rate-limited in-process in `AuthService`.

### LLM gateway

`app/llm/profiles.json` declares model profiles (endpoint, `${ENV_VAR}` placeholders for model IDs, context limit, generation defaults, capability flags, allowed/disallowed request fields, fallback profile). `ModelProfileRegistry` expands the env placeholders and validates fallback references at startup; `CapabilityChecker` rejects request fields the profile does not support and inlines system messages for models that lack a system role.

`LLMGateway.generate_text` handles the failure ladder: a parameter-compatibility rejection retries with a minimal body (`model`/`messages`/`temperature`/`max_tokens`), and a fallback-eligible provider error re-runs against `fallback_model_profile_id`. `generate_json` appends a JSON-only instruction, parses tolerantly, and does exactly one strict retry at `temperature=0`. Errors never raise out of `generate_text`; they come back as a `NormalizedLLMResponse` with `error_type` set, so callers check `result.ok`.

Provider and model identity are deliberately hidden from clients: `ModelProfile.public_dict()` / `NormalizedLLMResponse.public_dict()` return `"managed"` and a generic profile id, and `<think>` reasoning is stripped from both buffered and streamed output. Keep new response fields out of the public payloads unless they are safe to expose.

Every model call should be followed by `store.record_model_run(...)` (latency, tokens, retries, status) before the response is returned — see `app/api/chat.py` and `app/api/study.py`.

### Per-user models

Students can point StudyOS at their own OpenAI-compatible endpoint. `app/llm/user_models.py`
holds `UserModelStore` (one `user_model_settings` row per user, API key encrypted with
`SecretBox`) and `build_user_profile`, which turns those settings into a `ModelProfile` that
never enters the shared registry. `ModelProfile.api_key_value` carries the key so the
transport does not read the environment for it.

`app/api/model_context.py` is the single place routers ask which model to use:
`resolve_model_for_user(request, user_id)` returns `(profile_override, profile_id)` — the
override when the user saved a usable config, otherwise `None` plus the managed profile id,
and a 503 when neither is configured. Pass `profile_override=` down every gateway call
(`generate_text`, `generate_json`, `generate_stream` and their wrappers all accept it) and
`profile_id=None` alongside it. The user's profile keeps the managed profile as its
`fallback_model_profile_id` unless they opted out, so the existing failure ladder covers
provider outages.

`/api/settings/model` (GET/PUT/DELETE, plus `POST /test` and `POST /catalog`) is the only
route that touches these settings; it returns `public_dict()`, which carries a masked key
hint and never the key itself.

### RAG

Ingestion (`DocumentStore.ingest`): extract per-page sections (pypdf / python-docx / decoded text) → 700-word chunks with 100-word overlap → embed → upsert vectors → flip document status to `indexed` (or `failed`, with the error persisted). Blocking work is pushed through `asyncio.to_thread`.

Retrieval (`DocumentStore.retrieve`) is hybrid: `0.72 * cosine + 0.28 * lexical-overlap`, with a `+0.35` lexical bonus for an exact phrase hit; candidates below a vector floor with no lexical signal are dropped. Study-tool generation instead uses `get_study_chunks`, which builds a *document-balanced* context under a character budget so one long upload cannot crowd out the others, optionally reserving a third of the budget for focus-matched chunks.

The "General study session" (or the oldest one) is treated as the default workspace: queries for it also match rows with a `NULL` `study_session_id`, which is how pre-workspace data stays visible. `_is_default_study_session` encodes this.

### MCP server

`app/mcp/` exposes StudyOS to Claude, ChatGPT and other MCP clients at `POST /mcp`,
mounted by `create_app()` when `MCP_ENABLED` is true. It is stateless Streamable
HTTP: one JSON-RPC message per request, one JSON response, no SSE stream.

- `oauth.py` — the backend is its own OAuth 2.1 authorization server: dynamic
  client registration, authorization code + PKCE (`S256` required), rotating
  refresh tokens, revocation. Tokens are opaque and stored only as SHA-256
  hashes in `oauth_tokens`.
- `routes.py` — discovery documents, `/oauth/*` (the sign-in and consent page is
  served by the backend, carrying a signed short-lived login ticket because the
  consent POST is cross-site), the `/mcp` endpoint, and `/api/mcp/connections`
  for the web app.
- `protocol.py` — JSON-RPC dispatch. Tool *execution* failures come back as a
  result with `isError`; only protocol faults become JSON-RPC errors.
- `tools.py` — the tool catalogue. Handlers receive a `ToolContext` (store,
  gateway, `user_id`, and a `resolve_model` callable) and must pass `user_id`
  into every store call, the same per-user scoping invariant as the routers.

New MCP tools that generate text call `run_chat` / `run_study_tool` from
`app/api/chat.py` and `app/api/study.py` rather than re-implementing prompts, and
pass the `profile_override` from `context.resolve_model()` so a student's own
model is used. `MCPCorsMiddleware` (added last, so it wraps the credentialed
`CORSMiddleware`) opens CORS on the bearer-authenticated MCP and OAuth paths only.

### Schema changes

`Database.initialize()` runs `create_all` plus a hand-written `_migrate_schema()` that adds missing columns/indexes via raw `ALTER TABLE`. There is no Alembic. New columns need both a model field and a guarded statement there, written to work on SQLite and PostgreSQL.

## Frontend architecture

Next.js App Router with `output: "export"` — **no server components with server-side data, no route handlers, no middleware**; everything is client-side and talks to the backend from the browser. Pages: `/` (dashboard), `/documents`, `/chat`, `/study-tools`, `/settings`.

`lib/api.ts` is the only place that touches `fetch`. It sends `credentials: "include"`, attaches the in-memory CSRF token to mutations, and dispatches a `studyos-auth-required` window event on 401 which `auth-provider` listens for to bounce the user to sign-in. Add backend calls here with their response types rather than fetching from components.

State lives in three nested providers (see `app/layout.tsx` / `components/app-shell.tsx`):

- `auth-provider` — current user, CSRF token, clears persisted state on logout/expiry.
- `study-workspace-provider` — active study session, persisted in `localStorage` (`studyos.active-workspace-id.v1`), auto-creating a "General study session" when none exist.
- `study-job-provider` — a `localStorage`-backed queue (`studyos.study-jobs.v1`) that runs one study-tool generation at a time so navigation does not cancel it, and renders the floating status pill. Jobs and their results are browser-local only; they are not persisted server-side.

Styling is Tailwind 4 via `@tailwindcss/postcss` with colors written as inline hex values in class names; `lucide-react` supplies icons.

## Conventions

- Backend modules open with `from __future__ import annotations`; dataclasses are `frozen=True, slots=True` where practical.
- Tests are `unittest` classes (`TestCase` / `IsolatedAsyncioTestCase`) executed by pytest; async tests use `IsolatedAsyncioTestCase`. Fakes live in `tests/helpers.py` (`make_profile`, `FakeTransport`) — tests never hit a network, and file-backed tests write to `backend/tests/.runtime-data` and clean it up in `tearDown`.
- User-facing API errors are generic ("The AI assistant is temporarily unavailable"); the specific provider error goes to the `model_runs` row instead.
- Structured LLM output is always validated with Pydantic models before it leaves the API (`MCQPayload`, `FlashcardPayload` in `app/api/study.py`), and `_normalize_items` tolerates common key aliases the model may emit.

## Deployment

`render.yaml` deploys the exported frontend as a Render static site and the backend as a Python web service, wiring `FRONTEND_URL` and `NEXT_PUBLIC_API_BASE_URL` through `fromService` references (bare hostnames get `https://` prefixed in code). `DEPLOY_FREE.md` has the full walkthrough. `docker-compose.yml` provides local PostgreSQL 16 only.
