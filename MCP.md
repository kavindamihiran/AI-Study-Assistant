# StudyOS MCP server

StudyOS ships a **remote MCP server**, so a student can add their StudyOS
account to Claude, ChatGPT, or any other MCP client and work with their own
uploaded course material straight from that chat — no need to open the web app.

The server lives inside the FastAPI backend (`backend/app/mcp/`) and is served
from the same deployment as the REST API.

---

## Connecting from a chat app

The address to paste is the backend origin plus `/mcp`:

```
https://<your-backend-host>/mcp
```

Locally that is `http://127.0.0.1:8000/mcp`. Students can copy it from
**Settings → Connected chat apps**, which also lists (and disconnects) every
app that currently has access.

**Claude** (web, desktop): Settings → Connectors → *Add custom connector* →
paste the URL → Connect. Claude registers itself, opens the StudyOS sign-in and
consent page, and the tools appear in the chat.

**ChatGPT**: Settings → Connectors (developer mode) → *Add* → paste the URL →
authenticate. StudyOS also exposes the `search` and `fetch` tools ChatGPT deep
research expects.

**Claude Code / other CLI clients**:

```bash
claude mcp add --transport http studyos https://<your-backend-host>/mcp
```

Every client goes through the same OAuth flow: it registers itself, the student
signs in to StudyOS in a browser, approves the connection, and the client gets
a token scoped to that one account.

---

## Tools

| Tool | What it does |
| --- | --- |
| `list_study_sessions` | List the student's study sessions (workspaces) |
| `create_study_session` | Create a new workspace |
| `list_documents` | List uploaded documents with ids and indexing status |
| `get_document` | Metadata and status for one document |
| `add_note` | Save chat text as a markdown document and index it |
| `delete_document` | Delete a document and its indexed content (destructive) |
| `search_notes` | Hybrid semantic + keyword search, returns passages with citations |
| `ask_notes` | Grounded answer with citations, saved to StudyOS chat history |
| `generate_summary` | Structured study summary from selected documents |
| `generate_flashcards` | Active-recall flashcards |
| `generate_mcqs` | Multiple-choice questions with answers and explanations |
| `generate_study_plan` | Day-by-day study plan |
| `list_chat_sessions` / `get_chat_session` | Read StudyOS chat history |
| `search` / `fetch` | ChatGPT deep-research compatible retrieval |

The generation tools use the model the student configured in Settings (their own
OpenAI-compatible key) and fall back to the server-managed model, exactly like
the web app — the MCP layer calls the same `run_chat` / `run_study_tool`
services the HTTP routes use.

---

## How the server is built

`backend/app/mcp/` holds four modules:

- **`oauth.py`** — the OAuth 2.1 authorization server: dynamic client
  registration (RFC 7591), authorization code + PKCE, rotating refresh tokens,
  revocation (RFC 7009). Access and refresh tokens are random opaque strings
  stored only as SHA-256 hashes, in the `oauth_tokens` table.
- **`protocol.py`** — JSON-RPC 2.0 dispatch for MCP: `initialize`, `ping`,
  `tools/list`, `tools/call`, and empty `resources`/`prompts` listings.
  Protocol versions `2025-06-18`, `2025-03-26` and `2024-11-05` are accepted.
- **`tools.py`** — the tool catalogue and handlers. Every handler takes a
  `ToolContext` carrying the authenticated `user_id` and passes it into
  `DocumentStore`, so a connected chat can only reach its own account's rows.
- **`routes.py`** — discovery documents, the OAuth endpoints and the `/mcp`
  endpoint itself, plus `/api/mcp/connections` for the web app.

### Endpoints

| Path | Purpose |
| --- | --- |
| `POST /mcp` | The MCP endpoint (Streamable HTTP, JSON responses) |
| `GET /.well-known/oauth-protected-resource` | Points clients at the authorization server |
| `GET /.well-known/oauth-authorization-server` | Authorization server metadata |
| `POST /oauth/register` | Dynamic client registration |
| `GET/POST /oauth/authorize` | Sign-in and consent screen |
| `POST /oauth/token` | Code exchange and refresh |
| `POST /oauth/revoke` | Token revocation |
| `GET/DELETE /api/mcp/connections` | Manage connections from the web app |

The server is **stateless**: each POST carries a complete JSON-RPC message and
gets a complete JSON response, so there is no SSE stream and no session id to
keep alive (`GET /mcp` answers `405`).

### The sign-in and consent page

`/oauth/authorize` is served by the backend itself. If the browser already has
a StudyOS session cookie it shows a consent screen; otherwise it shows a
sign-in form that authenticates against the same `AuthService` (and the same
rate limiting) as the web app.

Because the consent form is submitted cross-site, a `SameSite=lax` session
cookie is not sent with it. The page therefore carries a **signed, 15-minute
login ticket** (HMAC over the user id, keyed by `MCP_SIGNING_SECRET`) that
binds the approval to the identity established on the page.

### Security properties

- PKCE with `S256` is **required**; plain challenges are rejected.
- `redirect_uri` must exactly match one registered by the client.
- Authorization codes are single use and expire after 5 minutes.
- Refresh rotates the whole grant: the old access and refresh tokens stop
  working immediately.
- Revoking a token — from `/oauth/revoke` or from Settings — kills the whole
  grant.
- Tokens carry a `user_id`; every store call is filtered by it, so one
  account's connector can never read another account's documents.
- CORS is wide open **only** on `/mcp`, `/.well-known/*` and the token
  endpoints, which are bearer-authenticated and never read cookies. The app's
  own credentialed API keeps its narrow allow-list.

---

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `MCP_ENABLED` | `true` | Set to `false` to remove the MCP and OAuth routes entirely |
| `PUBLIC_BASE_URL` | derived from the request | The externally reachable backend origin; set it in production so discovery advertises the right URLs behind a proxy |
| `MCP_SIGNING_SECRET` | random per process | Signs consent tickets — set a long random value |
| `MCP_ACCESS_TOKEN_MINUTES` | `60` | Access token lifetime |
| `MCP_REFRESH_TOKEN_DAYS` | `30` | Refresh token lifetime |

`render.yaml` already wires `PUBLIC_BASE_URL` to the API service host and
generates `MCP_SIGNING_SECRET`.

---

## Testing it by hand

```bash
# 1. Discovery
curl http://127.0.0.1:8000/.well-known/oauth-protected-resource

# 2. Register a client
curl -X POST http://127.0.0.1:8000/oauth/register \
  -H 'Content-Type: application/json' \
  -d '{"client_name":"Test","redirect_uris":["http://localhost:9999/callback"]}'

# 3. Open /oauth/authorize?... in a browser, approve, exchange the code at
#    /oauth/token, then call the endpoint:
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

The automated coverage lives in `backend/tests/test_mcp.py` (OAuth flow, PKCE,
code replay, refresh rotation, revocation, tool dispatch, and cross-account
isolation).
