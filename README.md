# AI Study Assistant

This repository currently contains the backend's model-compatibility foundation:

- configuration-driven model profile registry
- provider-neutral LLM Gateway
- OpenAI-compatible NVIDIA NIM transport
- response normalization for OpenAI and LangChain-style responses
- hidden reasoning removal
- tolerant JSON extraction and repair
- minimal-body retry and profile fallback
- FastAPI model profile, switch, and connection-test endpoints

## Configure

Create `backend/.env` from `backend/.env.example` and set `NVIDIA_API_KEY`.
Set the model ID environment variable for every profile you intend to use. The
profile names are stable application identifiers; NVIDIA catalog model IDs stay
in environment configuration.

Profiles live in `backend/app/llm/profiles.json`. A different registry file can
be selected with `MODEL_PROFILES_PATH`.

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --env-file .env
```

Useful endpoints:

- `GET /health`
- `GET /ready`
- `GET /api/models/profiles`
- `GET /api/models/active`
- `POST /api/models/switch`
- `POST /api/models/test`

## Test

The core suite has no network or API-key requirement:

```powershell
cd backend
python -m unittest discover -s tests -v
```

All future LangGraph nodes should depend on `LLMGateway`, never directly on a
provider SDK.
