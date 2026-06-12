# StudyOS

StudyOS is a full-stack AI study assistant that turns uploaded course material
into citation-grounded answers, summaries, MCQs, flashcards, and study plans.
Documents, chats, and generated work are organized into separate subject
sessions.

## Technical Highlights

| Area | Technology |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Backend | FastAPI, Python 3.12+, Pydantic |
| Authentication | Password hashing, HttpOnly cookies, CSRF protection |
| Database | SQLAlchemy 2 with SQLite locally and PostgreSQL in production |
| Production DB | Neon PostgreSQL, replaceable with any standard PostgreSQL service |
| RAG | Custom retrieval-augmented generation pipeline |
| Embeddings | Local 384-dimensional feature hashing or hosted embeddings |
| Vector store | SQL-backed vectors by default, optional Pinecone adapter |
| LLM integration | Custom provider-agnostic OpenAI-compatible gateway |
| Document parsing | pypdf and python-docx |
| Testing | Pytest, unittest, FastAPI TestClient |
| Deployment | Render static site, Render FastAPI service, Neon PostgreSQL |
| Local infrastructure | Docker Compose with PostgreSQL 16 |

The LLM gateway, model registry, RAG pipeline, fallback routing, response
normalization, and structured-output repair are custom implementations. This
keeps model behavior explicit, lightweight, and independently testable.

## Features

- Upload PDF, DOCX, Markdown, and plain-text notes.
- Extract and chunk document text while preserving PDF page numbers.
- Ask questions using selected documents as the only knowledge source.
- Show citations, quoted snippets, filenames, and page numbers.
- Generate summaries, MCQs, flashcards, and study plans.
- Validate structured MCQ and flashcard output with Pydantic.
- Create independent study sessions for different subjects.
- Register and sign in before using the workspace.
- Keep each user's study sessions, uploads, chats, and generated work isolated.
- Save and restore chat conversations.
- Queue study-tool generation while navigating between pages.
- Search pages, documents, and saved conversations.
- Reindex and delete documents.
- Delete a study session together with its documents and chats.
- Store model latency, token usage, retries, and run status.
- Keep provider credentials and model identifiers server-side.
- Enforce user ownership on sessions, documents, chats, and generated work.

## Architecture

```mermaid
flowchart LR
    U[Browser] --> F[Next.js Frontend]
    F -->|REST API| A[FastAPI Backend]

    A --> D[Document Ingestion]
    D --> X[PDF / DOCX / Text Extraction]
    X --> C[Chunking]
    C --> E[Embedding Provider]
    E --> V[Vector Store]

    A --> R[Hybrid RAG Retrieval]
    R --> V
    R --> G[LLM Gateway]
    G --> L[Managed AI Endpoint]

    A --> DB[(SQLite / PostgreSQL)]
    D --> DB
    R --> DB
    G --> DB
```

## RAG Pipeline

### Document ingestion

```text
Upload
  -> validate file type and size
  -> extract text
  -> create overlapping chunks
  -> generate embeddings
  -> persist chunks and vectors
  -> mark document as indexed
```

Documents are split into 700-word chunks with 100-word overlap.

### Question answering

```text
Question
  -> create query embedding
  -> retrieve vector candidates
  -> calculate lexical relevance
  -> combine scores
  -> select the best chunks
  -> generate an answer from those chunks only
  -> return citations
```

Retrieval combines:

- 72% vector similarity
- 28% lexical relevance
- an additional boost for exact phrase matches

For large multi-document study requests, the backend builds
document-balanced context so one long document does not consume the entire
prompt budget.

## LLM Gateway

The gateway prevents product features from depending directly on one model or
provider.

Model profiles define:

- model and endpoint environment variables
- context limits and generation defaults
- streaming and structured-output capabilities
- system-message compatibility
- allowed and rejected request parameters
- fallback model profiles

The gateway supports:

- capability-aware request construction
- automatic system-message adaptation
- retrying rejected parameters with a minimal request body
- fallback routing for rate limits and provider failures
- normalized text, usage, tool-call, and error responses
- tolerant JSON parsing and one strict structured-output retry
- filtering hidden reasoning from normal and streaming responses

Profiles are configured in
`backend/app/llm/profiles.json`, while real credentials and model IDs remain in
environment variables.

## Security Model

StudyOS uses account-scoped data access:

- passwords are hashed server-side with `scrypt`
- sessions use random opaque tokens stored as `HttpOnly` cookies
- only a SHA-256 hash of each session token is stored in the database
- unsafe requests require a per-session `X-CSRF-Token`
- every study session, document, chat, and model run is filtered by user ID
- public registration is rate-limited to reduce signup abuse
- logout and expired sessions clear browser-persisted chat and job state

For a public deployment, keep `AUTH_REGISTRATION_ENABLED=true` so new users can
create accounts. For a private personal deployment, set it to `false` after the
first account is created.

## Persistence

SQLAlchemy stores:

| Table | Contents |
| --- | --- |
| `study_sessions` | Subject workspaces |
| `documents` | File metadata and indexing status |
| `document_chunks` | Extracted text and page metadata |
| `chunk_embeddings` | Embedding vectors stored as JSON |
| `chat_sessions` | Saved conversations |
| `chat_messages` | Messages and citations |
| `model_runs` | Latency, usage, retries, and errors |

SQLite provides zero-configuration local development. PostgreSQL is used for
durable hosted data. Any service providing a standard PostgreSQL connection
string can replace Neon without application-code changes.

Browser `localStorage` preserves the active study session, current chat
request, and study-tool queue. Completed chat messages are persisted in the
database.

## Project Structure

```text
backend/
  app/api/          FastAPI routes
  app/database/     SQLAlchemy models and engine
  app/documents/    Extraction, chunking, and ingestion
  app/llm/          Model profiles, gateway, transport, normalization
  app/rag/          Embeddings and vector stores
  tests/            Backend and API tests

frontend/
  app/              Next.js pages
  components/       Shell, state providers, queue, Markdown renderer
  lib/api.ts        Typed backend client

docker-compose.yml  Local PostgreSQL
render.yaml         Free deployment Blueprint
DEPLOY_FREE.md      Complete hosting guide
```

## Local Setup

### Backend

```powershell
Copy-Item backend\.env.example backend\.env.local
cd backend
python -m venv .venv-api
.\.venv-api\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Required backend configuration:

```dotenv
AI_API_KEY=your-private-key
AI_BASE_URL=https://your-compatible-endpoint/v1
AI_DEFAULT_MODEL_ID=your-model-id
ACTIVE_MODEL_PROFILE_ID=study_ai_default
FRONTEND_URL=http://127.0.0.1:3200
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
```

Without `DATABASE_URL`, the application uses
`backend/data/study_assistant.db`.

### Frontend

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev -- --hostname 127.0.0.1 --port 3200
```

Open `http://127.0.0.1:3200`.

API documentation:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

## Optional PostgreSQL

```powershell
docker compose up -d postgres
```

```dotenv
DATABASE_URL=postgresql+psycopg://study_assistant:study_assistant@127.0.0.1:5432/study_assistant
```

The database schema is created automatically at backend startup.

## Testing

```powershell
.\backend\.venv-api\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider
```

```powershell
cd frontend
npm run build
```

Current verified status:

```text
Backend: 23 tests passed
Frontend: production static build passed
```

Tests cover the model registry, capability checks, retries, fallback routing,
response normalization, hidden-reasoning filtering, JSON repair, extraction,
chunking, embeddings, retrieval, document APIs, citations, study generation,
chat persistence, and session deletion.

## Deployment

The included `render.yaml` deploys:

- the exported Next.js frontend as a Render static site
- FastAPI as a Render Python web service
- persistent application data through an external PostgreSQL `DATABASE_URL`

The Blueprint uses Render `fromService` references to connect the two services:

```text
Backend FRONTEND_URL             <- frontend service hostname
Frontend NEXT_PUBLIC_API_BASE_URL <- backend service hostname
```

The application converts these hostnames to HTTPS automatically. Public Render
URLs therefore do not need to be hard-coded or committed.

Before a new deployment, give both services unique non-personal names in
`render.yaml` and update the matching `fromService.name` references. Existing
Render services should either keep their current names with URLs configured
manually, or be replaced by a fresh Blueprint deployment. Changing a service
name in the YAML can create another service instead of renaming the existing
one.

The recommended $0 setup uses Neon PostgreSQL. Supabase PostgreSQL can be used
by replacing only `DATABASE_URL`.

See [DEPLOY_FREE.md](DEPLOY_FREE.md) for the complete deployment process.

## Security

- API keys are backend-only.
- Local environment files are ignored by Git.
- Public APIs hide provider and model identifiers.
- Hidden model reasoning is removed from user-facing output.
- User data is isolated by account at the API and database-query layers.
- Session cookies are `HttpOnly`; mutation requests require CSRF tokens.
- Upload types and sizes are validated.
- Generated structured data is schema-validated.
- CORS is restricted to configured frontend origins.

## Current Limitations

- Authentication is implemented, but advanced features such as password reset,
  email verification, MFA, and external identity providers are not included yet.
- Scanned PDFs require OCR, which is not currently included.
- Original uploads need object storage for durable production retention.
- Study-tool jobs and results are currently browser-local.
- SQL vector search performs a linear scan and is intended for small datasets.
- The local hashing embedder is cheaper but less semantic than hosted models.
- Free hosting introduces cold starts and has no uptime guarantee.

## License

This project is open source under the [MIT License](LICENSE).
