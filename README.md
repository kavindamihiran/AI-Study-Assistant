# StudyOS

StudyOS is a full-stack AI study workspace that converts uploaded course
material into grounded conversations, summaries, multiple-choice questions,
flashcards, and study plans.

The project was designed around two difficult engineering problems:

1. Keeping AI integration stable when models expose different capabilities,
   request parameters, response formats, and failure behavior.
2. Keeping documents, conversations, and generated work separated into
   persistent subject-specific study sessions.

The application uses a provider-agnostic, OpenAI-compatible LLM gateway rather
than coupling product code directly to one model vendor. Provider credentials,
model identifiers, and hidden reasoning remain server-side.

## Product Features

- Upload and index PDF, DOCX, Markdown, and plain-text notes.
- Ask questions using selected documents as the only allowed knowledge source.
- Display page-aware citations and quoted source snippets with answers.
- Generate structured MCQs and flashcards from uploaded material.
- Generate comprehensive summaries and multi-day study plans.
- Organize documents, chats, and study work by subject session.
- Create, switch, collapse, search, and delete study sessions.
- Restore saved chat conversations.
- Continue chat requests while navigating between application pages.
- Queue study-tool jobs and restore them after a page reload.
- Render AI Markdown as styled headings, lists, tables, bold text, and code.
- Reindex or delete uploaded documents.
- Record model latency, token usage, retry count, and run status.
- Use SQLite locally and PostgreSQL in hosted environments.
- Use local deterministic embeddings by default, with hosted embeddings and
  Pinecone available as optional adapters.

## Technology Stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Frontend framework | Next.js 16 App Router | Routes, static export, application composition |
| UI runtime | React 19 | Client components, context providers, state and effects |
| Language | TypeScript 5.9 | Typed frontend API contracts and UI logic |
| Styling | Tailwind CSS 4 | Responsive layout and component styling |
| Icons | Lucide React | Accessible interface iconography |
| Backend framework | FastAPI | REST API, validation, CORS, uploads, health checks |
| Backend runtime | Python 3.12+ | Document, RAG, gateway, and persistence services |
| Validation | Pydantic | API request and generated-data validation |
| ORM | SQLAlchemy 2 | Database models, sessions, queries, and schema creation |
| Local database | SQLite | Zero-configuration local persistence |
| Hosted database | PostgreSQL with Psycopg 3 | Durable production persistence |
| PDF extraction | pypdf | Page-aware text extraction |
| DOCX extraction | python-docx | Paragraph extraction from Word documents |
| LLM transport | Python `urllib` | Dependency-light OpenAI-compatible HTTP and SSE calls |
| Embeddings | Local feature hashing or hosted API | Query and document vector generation |
| Vector storage | SQL JSON vectors or Pinecone | Similarity retrieval and document filtering |
| Testing | Pytest, unittest, FastAPI TestClient | Gateway, parsing, ingestion, RAG, and API tests |
| Local infrastructure | Docker Compose | Optional PostgreSQL 16 development database |
| Deployment | Render Blueprint and Neon | Free static hosting, API hosting, and PostgreSQL |

This project currently uses custom orchestration rather than LangChain. The
gateway, retrieval pipeline, structured-output repair, fallback behavior, and
observability are implemented directly so their behavior remains explicit and
testable.

## System Architecture

```mermaid
flowchart LR
    U[Browser] --> F[Next.js static frontend]
    F -->|REST and multipart upload| A[FastAPI API]

    A --> S[Study session service]
    A --> D[Document ingestion service]
    A --> R[RAG retrieval service]
    A --> G[LLM gateway]

    D --> X[PDF, DOCX, TXT, MD extraction]
    X --> C[Overlapping chunks]
    C --> E[Embedding provider]
    E --> V[Vector store]

    R --> E
    R --> V
    R --> DB[(SQLite or PostgreSQL)]
    S --> DB
    D --> DB
    G --> P[Managed AI endpoint]
    G --> DB
```

### Frontend State Architecture

The root layout composes three React context providers:

- `StudyWorkspaceProvider` loads subject sessions from the backend and stores
  the active session ID in `localStorage`.
- `ChatProvider` preserves the visible conversation, selected documents, and
  an in-flight request so navigation does not discard current chat work.
- `StudyJobProvider` maintains a sequential browser-side queue of up to 20
  summary, MCQ, flashcard, and plan jobs.

Chats and study sessions are persisted in the database. The active browser
request and study-tool queue are persisted in `localStorage`. Study-tool output
is therefore browser-local in the current version, while saved chat messages
are server-persistent.

## Core Workflows

### 1. Document Ingestion

```text
Upload
  -> validate extension and size
  -> extract readable text
  -> preserve PDF page numbers
  -> split into 700-word chunks with 100-word overlap
  -> persist document and chunk metadata
  -> generate embeddings
  -> upsert vectors
  -> mark document as indexed
```

Supported extensions:

- `.pdf`
- `.docx`
- `.txt`
- `.md`

The document status moves through `processing`, `indexed`, or `failed`.
Reindexing regenerates embeddings from database-backed chunks, so it does not
depend on the original upload still being present.

### 2. Retrieval-Augmented Chat

```text
Question
  -> embed query
  -> retrieve vector candidates
  -> calculate lexical overlap
  -> combine vector and lexical scores
  -> select the five strongest chunks
  -> build a source-labelled prompt
  -> generate an answer restricted to retrieved notes
  -> save messages, citations, and model-run metrics
```

Retrieval is hybrid:

- 72% vector similarity
- 28% lexical relevance
- exact phrase matches receive an additional lexical boost

Answers contain document IDs, filenames, page numbers when available, chunk
IDs, quoted snippets, and relevance scores.

### 3. Study Material Generation

The study endpoints support:

- `summary`: broad Markdown study notes
- `mcq`: validated structured questions, options, answers, and explanations
- `flashcards`: validated front/back active-recall cards
- `plan`: a practical 1-30 day study schedule

When selected material exceeds the context budget, the backend builds a
document-balanced sample instead of taking only the beginning of the first
file. An optional topic gets focused retrieval priority while the remaining
budget continues to cover the broader documents.

### 4. Subject Session Isolation

Each study session owns its own:

- uploaded documents
- document chunks and embeddings
- chat sessions and messages
- model-run history associated with those chats

Deleting a study session removes its related documents, vectors, conversations,
run records, and locally stored source files. When no session remains, the
frontend creates a new general session automatically.

## LLM Gateway

The LLM gateway isolates the rest of the application from model-specific
behavior.

### Model Profile Registry

Profiles are declared in `backend/app/llm/profiles.json` and resolved from
environment variables at startup. A profile describes:

- internal profile ID and display label
- base URL and model ID
- API-key environment variable
- context limit and generation defaults
- streaming, JSON, tool-calling, reasoning, vision, and system-message support
- allowed and disallowed request fields
- response parser and prompt style
- optional fallback profile

This makes model changes configuration work instead of product-code changes.

### Request Compatibility

Before sending a request, the gateway:

1. Resolves and validates the selected profile.
2. Adapts system messages when a model does not support the system role.
3. Rejects unsupported extra request fields.
4. Removes fields explicitly disallowed by that profile.
5. Retries parameter-compatibility failures with a minimal request body.
6. Uses a configured fallback profile for availability and rate-limit errors.

### Response Normalization

Provider responses are converted into one internal response type containing:

- visible answer text
- parsed JSON
- normalized tool calls
- content blocks
- token usage
- finish reason
- retry count
- latency
- typed error information

Reasoning fields and `<think>...</think>` blocks are separated from visible
content. Streaming output also filters split reasoning tags before yielding
text. Hidden reasoning is never returned by the product APIs.

### Structured Output Reliability

MCQ and flashcard generation use a tolerant JSON pipeline:

1. Ask for JSON-only output.
2. Parse plain JSON, fenced JSON, or a balanced JSON object inside extra text.
3. Repair trailing commas.
4. Safely accept Python-style literals only when they contain JSON-compatible
   values.
5. Retry once with a stricter prompt when local repair cannot recover output.
6. Validate the final structure with Pydantic before returning it.

## RAG and Vector Storage

### Default Local Embeddings

The default `HashingEmbeddingProvider` is:

- deterministic
- local and network-free
- 384-dimensional by default
- based on token and bigram feature hashing
- normalized for cosine similarity

It keeps local development and small free deployments inexpensive. It is not a
semantic transformer model, so hosted embeddings can be enabled when retrieval
quality is more important.

### Vector Store Adapters

`LocalSQLVectorStore` stores embedding arrays as JSON in the application
database and computes cosine similarity in Python. This is simple and portable
for small datasets.

`PineconeVectorStore` is an optional adapter with:

- batched upserts
- metadata document filtering
- namespace isolation
- remote health checking
- document-level vector deletion

Both implementations conform to the same vector-store protocol.

## Persistence Model

| Table | Purpose |
| --- | --- |
| `study_sessions` | Subject-level workspace metadata |
| `documents` | File metadata, indexing state, ownership, and source path |
| `document_chunks` | Extracted text with order and PDF page metadata |
| `chunk_embeddings` | Vector JSON, dimensions, and embedding model |
| `chat_sessions` | Saved conversations scoped to a study session |
| `chat_messages` | User/assistant messages and citation JSON |
| `model_runs` | Latency, usage, status, retries, and execution stage |

SQLAlchemy creates missing tables at startup. A small compatibility migration
adds study-session foreign keys to databases created by older versions.
Legacy JSON document indexes are imported once when an empty database starts.

## API Surface

Interactive FastAPI documentation is available locally at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Process health check |
| `GET` | `/ready` | AI, database, and vector readiness |
| `GET` | `/api/study-sessions` | List subject sessions |
| `POST` | `/api/study-sessions` | Create a subject session |
| `GET` | `/api/study-sessions/{id}` | Read a subject session |
| `DELETE` | `/api/study-sessions/{id}` | Delete a session and scoped data |
| `GET` | `/api/documents` | List documents, optionally by session |
| `GET` | `/api/documents/{id}` | Read document metadata |
| `POST` | `/api/documents/upload` | Upload and index a document |
| `POST` | `/api/documents/{id}/reindex` | Regenerate document vectors |
| `DELETE` | `/api/documents/{id}` | Delete a document and vectors |
| `POST` | `/api/chat` | Ask a grounded question |
| `GET` | `/api/chat/sessions` | List saved chats |
| `GET` | `/api/chat/sessions/{id}` | Restore a saved chat |
| `DELETE` | `/api/chat/sessions/{id}` | Delete a saved chat |
| `POST` | `/api/study/summary` | Generate a grounded summary |
| `POST` | `/api/study/mcq` | Generate validated MCQs |
| `POST` | `/api/study/flashcards` | Generate validated flashcards |
| `POST` | `/api/study/plan` | Generate a grounded study plan |

The public product API intentionally does not expose provider names, model
identifiers, API keys, raw provider responses, or hidden reasoning.

## Repository Structure

```text
.
|-- backend/
|   |-- app/
|   |   |-- api/             # FastAPI routes and request validation
|   |   |-- database/        # SQLAlchemy engine and ORM models
|   |   |-- documents/       # Extraction, chunking, ingestion, persistence
|   |   |-- llm/             # Profiles, gateway, transport, normalization
|   |   |-- rag/             # Embeddings and vector-store adapters
|   |   |-- config.py        # Environment-backed application settings
|   |   `-- main.py          # Dependency composition and FastAPI app
|   |-- tests/               # Unit and API integration tests
|   |-- .env.example
|   `-- pyproject.toml
|-- frontend/
|   |-- app/                 # Next.js App Router pages and global styles
|   |-- components/          # Shell, providers, queue, Markdown renderer
|   |-- lib/api.ts           # Typed REST client
|   |-- .env.example
|   |-- next.config.ts
|   `-- package.json
|-- docker-compose.yml       # Optional local PostgreSQL
|-- render.yaml              # Render frontend/API deployment Blueprint
|-- DEPLOY_FREE.md           # Full free-hosting guide
`-- README.md
```

## Local Development

### Prerequisites

- Python 3.12 or newer
- Node.js 20 or newer
- npm
- An OpenAI-compatible managed AI endpoint and key
- Docker Desktop only when using the optional local PostgreSQL service

### 1. Configure The Backend

```powershell
Copy-Item backend\.env.example backend\.env.local
```

Set at least:

```dotenv
AI_API_KEY=your-private-key
AI_BASE_URL=https://your-managed-ai-endpoint/v1
AI_DEFAULT_MODEL_ID=your-model-id
ACTIVE_MODEL_PROFILE_ID=study_ai_default
FRONTEND_URL=http://127.0.0.1:3200
```

Do not place private keys in `frontend/.env.local` or any `NEXT_PUBLIC_`
variable. Local environment files are ignored by Git.

### 2. Start The Backend

```powershell
cd backend
python -m venv .venv-api
.\.venv-api\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Without `DATABASE_URL`, the backend creates:

```text
backend/data/study_assistant.db
```

### 3. Start The Frontend

In a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev -- --hostname 127.0.0.1 --port 3200
```

Open `http://127.0.0.1:3200`.

## Optional PostgreSQL Development

Start PostgreSQL 16:

```powershell
docker compose up -d postgres
```

Add this to `backend/.env.local`:

```dotenv
DATABASE_URL=postgresql+psycopg://study_assistant:study_assistant@127.0.0.1:5432/study_assistant
```

The application creates its schema automatically at startup.

## Configuration Reference

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `AI_API_KEY` | Yes | None | Private managed-AI credential |
| `AI_BASE_URL` | Yes | None | OpenAI-compatible API base URL |
| `AI_DEFAULT_MODEL_ID` | Yes | None | Default model route |
| `AI_FAST_MODEL_ID` | Optional | None | Fast profile model route |
| `AI_ADVANCED_MODEL_ID` | Optional | None | Advanced profile model route |
| `AI_BALANCED_MODEL_ID` | Optional | None | Balanced profile model route |
| `AI_LONG_CONTEXT_MODEL_ID` | Optional | None | Long-context profile route |
| `ACTIVE_MODEL_PROFILE_ID` | No | `study_ai_default` | Active internal model profile |
| `MODEL_PROFILES_PATH` | No | Bundled JSON file | Alternative registry file |
| `LLM_REQUEST_TIMEOUT_SECONDS` | No | `90` | Provider request timeout |
| `FRONTEND_URL` | No | `http://localhost:3000` | Production CORS origin |
| `DATA_DIR` | No | `backend/data` | Upload and local DB directory |
| `MAX_UPLOAD_MB` | No | `25` | Upload size limit |
| `DATABASE_URL` | No | Local SQLite | SQLAlchemy database URL |
| `EMBEDDING_PROVIDER` | No | `local` | `local` or `hosted` |
| `EMBEDDING_DIMENSION` | No | `384` | Local or expected vector size |
| `AI_EMBEDDING_MODEL_ID` | Hosted only | None | Hosted embedding model |
| `VECTOR_STORE_PROVIDER` | No | `local` | `local` or `pinecone` |
| `PINECONE_API_KEY` | Pinecone only | None | Pinecone credential |
| `PINECONE_INDEX_HOST` | Pinecone only | None | Pinecone index hostname |
| `PINECONE_NAMESPACE` | No | `study-assistant` | Vector namespace |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend | Local API | Browser-visible API origin |

For Pinecone support:

```powershell
cd backend
python -m pip install -e ".[pinecone]"
```

## Testing And Verification

Run backend tests:

```powershell
.\backend\.venv-api\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider
```

Run the production frontend build:

```powershell
cd frontend
npm run build
```

The current suite covers:

- model profile parsing and fallback validation
- capability checks and system-message adaptation
- response normalization and hidden-reasoning separation
- malformed JSON recovery and strict retry behavior
- parameter-compatibility retries
- model fallback routing
- streaming reasoning filtering
- document extraction and chunking
- ingestion, embedding, retrieval, reindexing, and deletion
- session-scoped cascade deletion
- chat persistence and public response privacy
- grounded summary, MCQ, and flashcard APIs

Current verified status:

```text
Backend: 21 tests passed
Frontend: production static build passed
```

## Deployment

The repository includes a `render.yaml` Blueprint for:

- a Render static site serving the exported Next.js frontend
- a Render Python web service running FastAPI
- a Neon PostgreSQL database supplied through `DATABASE_URL`

Follow [DEPLOY_FREE.md](DEPLOY_FREE.md) for the complete setup, secret entry,
health verification, free-tier behavior, and custom-domain instructions.

The frontend is exported to `frontend/out`. Production credentials exist only
on the API service. The deployed backend stores durable application data in
PostgreSQL rather than Render's temporary filesystem.

## Security And Privacy Design

Implemented safeguards:

- private credentials are loaded only by the backend
- `.env` and `.env.local` files are ignored by Git
- the browser receives no provider or model identifiers
- unsupported model parameters are blocked per profile
- hidden reasoning is separated and omitted from public responses
- filenames are reduced to their basename before local storage
- uploads enforce extension and size checks
- generated MCQ and flashcard payloads are schema-validated
- CORS is restricted to configured frontend and local development origins
- static-site security headers disable MIME sniffing and restrict referrers

## Current Limitations

These are deliberate next-step boundaries rather than hidden claims:

- There is no authentication or per-user authorization yet. A publicly shared
  deployment is a shared workspace.
- Scanned/image-only PDFs are rejected because OCR is not implemented.
- The free deployment stores original upload bytes on an ephemeral filesystem.
  Extracted chunks, vectors, sessions, and chats remain durable in PostgreSQL.
- Study-tool jobs are a browser-side queue, not a server worker system.
- Study-tool results are stored in browser `localStorage`, not a backend table.
- Local SQL vector retrieval loads candidate vectors and performs a linear
  cosine scan, which is appropriate for small collections rather than scale.
- The local hashing embedder is inexpensive and deterministic but less semantic
  than a transformer embedding model.
- There is no malware scanning or content moderation for uploaded files.
- There are no automated browser end-to-end tests yet.
- Free hosting has cold starts, storage limits, and no uptime guarantee.

## Production Roadmap

The next production-focused milestones are:

1. Add authentication, users, ownership checks, and tenant isolation.
2. Move source files to durable object storage with signed access.
3. Move study generation to a durable server queue with job APIs.
4. Persist generated summaries, quizzes, flashcards, and plans in PostgreSQL.
5. Add OCR for scanned lecture material.
6. Add database migrations with Alembic.
7. Use a production vector index or PostgreSQL vector extension at scale.
8. Add request tracing, centralized logs, metrics, and alerting.
9. Add rate limiting, quotas, abuse controls, and upload malware scanning.
10. Add Playwright end-to-end coverage and continuous integration.

## Interview Walkthrough

A concise technical explanation of this project:

> StudyOS is a Next.js and FastAPI RAG application. Uploaded learning material
> is extracted, chunked, embedded, and stored with page metadata. Questions use
> hybrid vector and lexical retrieval before a provider-agnostic LLM gateway
> generates a citation-backed response. The gateway uses capability-based model
> profiles, request adaptation, minimal-body retries, fallback routing,
> response normalization, structured-output repair, and hidden-reasoning
> filtering. SQLAlchemy persists subject sessions, documents, vectors, chats,
> citations, and model-run telemetry in SQLite or PostgreSQL. The frontend uses
> React context and local persistence so active chat and study jobs survive
> navigation.

Key engineering decisions worth discussing:

- A profile registry prevents model-switching logic from leaking into product
  features.
- Custom gateway orchestration makes compatibility behavior explicit and easy
  to unit test.
- Hybrid retrieval improves exact-term matching over vector-only search.
- Document-balanced context selection avoids starving later documents.
- Structured output is repaired and validated before it reaches the UI.
- The storage interfaces allow local development and hosted infrastructure to
  use the same application services.
- Server-persistent chats and browser-persistent active jobs serve different
  durability needs, with a clear migration path to a real worker queue.

## License

No open-source license has been added yet. Unless a license is added, the source
code remains all rights reserved by its owner.
