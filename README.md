# StudyOS

StudyOS is an AI study workspace for turning course material into:

- grounded answers with document citations
- summaries and study plans
- multiple-choice practice questions
- flashcards
- reusable subject sessions
- saved conversations and background generation jobs

## Local Start

Backend:

```powershell
cd backend
python -m venv .venv-api
.\.venv-api\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3200
```

Open `http://127.0.0.1:3200`.

## Production Configuration

Copy `backend/.env.example` to `backend/.env.local` and set the managed AI
connection values. Local env files are ignored by git and loaded automatically
by the backend.

The browser only needs:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://your-api.example.com
```

Keep all private credentials in the backend environment. Never place private
keys in frontend variables.

## Data

The default local setup stores documents, chunks, vectors, sessions, chats, and
generation history in SQLite under `backend/data`.

For PostgreSQL:

```dotenv
DATABASE_URL=postgresql+psycopg://user:password@host:5432/database
```

The application creates its tables automatically.

## Health Checks

- `GET /health`
- `GET /ready`

## Tests

```powershell
.\backend\.venv-api\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider
```

```powershell
cd frontend
npm run build
```
