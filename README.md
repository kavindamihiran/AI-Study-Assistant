# AI Study Assistant

Working Next.js and FastAPI study workspace with:

- NVIDIA NIM model-profile registry and provider-neutral LLM Gateway
- PDF, TXT, Markdown, and DOCX ingestion
- SQLAlchemy persistence for documents, chunks, chat history, and model runs
- local persisted dense-vector search with hybrid lexical reranking
- optional PostgreSQL/Neon database configuration
- optional Pinecone vector database
- local hashing embeddings or NVIDIA NIM embeddings
- grounded RAG answers with backend-generated citations

## Local Quick Start

The default setup needs no database or vector service. It creates
`backend/data/study_assistant.db` and stores vectors in the database.

```powershell
cd backend
python -m venv .venv-api
.\.venv-api\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

```powershell
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3200
```

Open `http://127.0.0.1:3200`.

## Database

SQLite is used when `DATABASE_URL` is empty. Tables are initialized
automatically from the SQLAlchemy schema.

To run local PostgreSQL:

```powershell
docker compose up -d postgres
```

Then set:

```dotenv
DATABASE_URL=postgresql+psycopg://study_assistant:study_assistant@localhost:5432/study_assistant
```

For Neon, use its PostgreSQL connection string with the
`postgresql+psycopg://` scheme.

Persisted tables:

- `documents`
- `document_chunks`
- `chunk_embeddings`
- `chat_sessions`
- `chat_messages`
- `model_runs`

## Embeddings And Vector Search

Zero-setup local configuration:

```dotenv
EMBEDDING_PROVIDER=local
EMBEDDING_DIMENSION=384
VECTOR_STORE_PROVIDER=local
```

For NVIDIA semantic embeddings:

```dotenv
EMBEDDING_PROVIDER=nvidia
NVIDIA_EMBEDDING_MODEL_ID=nvidia/llama-nemotron-embed-1b-v2
EMBEDDING_DIMENSION=2048
```

For Pinecone, create a cosine index whose dimension matches the embedding
model, install the optional client, then configure its host:

```powershell
python -m pip install -e ".[pinecone]"
```

```dotenv
VECTOR_STORE_PROVIDER=pinecone
PINECONE_API_KEY=...
PINECONE_INDEX_HOST=...
PINECONE_NAMESPACE=study-assistant
```

Pinecone stores vectors and metadata while PostgreSQL/SQLite remains the source
of truth for document text, chunks, sessions, and model-run records.

## Model Profiles

Built-in NVIDIA profiles include default model IDs so a fresh backend restart
does not leave GLM, Kimi, DeepSeek, or Nemotron with blank configuration. You
can still override any profile from `.env`:

```dotenv
NVIDIA_DEFAULT_MODEL_ID=nvidia/nemotron-3-super-120b-a12b
NVIDIA_DEEPSEEK_V4_FLASH_MODEL_ID=deepseek-ai/deepseek-v3.1-terminus
NVIDIA_DEEPSEEK_V4_PRO_MODEL_ID=deepseek-ai/deepseek-v3.2
NVIDIA_GLM_5_1_MODEL_ID=z-ai/glm-5.1
NVIDIA_KIMI_K2_6_MODEL_ID=moonshotai/kimi-k2.6
```

## RAG Flow

1. Extract text and preserve PDF page numbers.
2. Split text into overlapping chunks.
3. Persist document and chunk metadata in SQL.
4. Generate and store dense embeddings.
5. Retrieve by vector similarity and lexical overlap.
6. Build a bounded context prompt.
7. Generate through the active LLM Gateway profile.
8. Return citations from retrieved chunk metadata.
9. Persist user/assistant messages and model-run telemetry.

## API

- `POST /api/documents/upload`
- `GET /api/documents`
- `GET /api/documents/{id}`
- `POST /api/documents/{id}/reindex`
- `DELETE /api/documents/{id}`
- `POST /api/chat`
- `GET /api/chat/sessions`
- `GET /api/chat/sessions/{id}`
- `DELETE /api/chat/sessions/{id}`
- `GET /api/models/profiles`
- `GET /api/models/active`
- `POST /api/models/switch`
- `POST /api/models/test`
- `GET /health`
- `GET /ready`

## Test

```powershell
cd backend
.\.venv-api\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

```powershell
cd frontend
npm run build
```
