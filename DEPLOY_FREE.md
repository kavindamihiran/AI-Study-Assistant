# Free Deployment Guide

This setup uses:

- Render Static Site for the exported Next.js frontend
- Render Free Web Service for the FastAPI backend
- Neon Free Postgres for sessions, documents, chunks, vectors, and chats

No private AI credentials are included in the frontend or repository.

## Reality Check

This is a good $0 personal deployment or public beta, but it is not a
reliability-grade production setup. Render explicitly recommends its free
instances for hobby projects and testing rather than production applications.
The API sleeps when idle and neither free service provides an uptime SLA.

The current application includes account login and per-user data isolation. For
public use, keep registration enabled so each visitor must create an account
before using the workspace.

## Important Before Production

Rotate the AI API key that was previously used during development. Treat any key
ever pasted into a chat, terminal transcript, screenshot, or issue as exposed.
Put the replacement key only in Render's secret environment-variable form.

The hosting can remain at $0 within free-tier limits. AI inference is billed or
limited separately by the configured AI service, so the complete application is
only $0 while that account has sufficient free allowance.

Existing local SQLite sessions and documents are not automatically copied to
Neon. The deployed app starts with a new empty database.

## 1. Push The Repository To GitHub

From the project root:

```powershell
git status
git add .
git commit -m "Prepare StudyOS for free deployment"
git push
```

Confirm that `backend/.env`, `backend/.env.local`, and `frontend/.env.local` are
not listed in the commit. They are ignored by the repository's `.gitignore`.

## 2. Create The Free Database

1. Create an account at <https://neon.tech/>.
2. Create a Free plan project.
3. Open the project's **Connect** dialog.
4. Select the pooled connection and copy its connection string. The hostname
   normally contains `-pooler`.
5. Keep the full URL ready for the Render setup. SSL settings in the copied URL
   should be preserved.

The backend accepts Neon's standard `postgresql://...` URL and creates all
required tables during its first startup.

## 3. Deploy Both Render Services

### Choose Unique Service Names

Before creating the Blueprint, open `render.yaml` and choose service names that
are available on Render. Keep the names generic and add a random suffix:

```yaml
services:
  - type: web
    name: studyos-api-your-suffix
    # ...
    envVars:
      - key: FRONTEND_URL
        fromService:
          type: web
          name: studyos-web-your-suffix
          property: host

  - type: web
    name: studyos-web-your-suffix
    # ...
    envVars:
      - key: NEXT_PUBLIC_API_BASE_URL
        fromService:
          type: web
          name: studyos-api-your-suffix
          property: host
```

Replace `your-suffix` with a non-personal value such as `a8f3c2`. Each service
name and its matching `fromService.name` must be identical.

`property: host` supplies a hostname without a protocol. The frontend and
backend automatically convert that value to an HTTPS URL, so no public Render
URL needs to be committed to the repository.

### Create The Blueprint

1. Create an account at <https://render.com/> and connect the GitHub account.
2. In the Render dashboard, select **New > Blueprint**.
3. Select this repository. Render detects the root `render.yaml`.
4. Enter these secret values when prompted:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | The pooled Neon connection string |
| `AI_API_KEY` | The newly rotated private API key |
| `AI_BASE_URL` | The private server-side compatible API base URL |
| `AI_DEFAULT_MODEL_ID` | The production model identifier |
| `AUTH_COOKIE_SECURE` | `true` |
| `AUTH_COOKIE_SAMESITE` | `none` |
| `AUTH_REGISTRATION_ENABLED` | `true` for public signup |

5. Apply the Blueprint and wait for both services to finish deploying.

Render assigns public addresses to both services. Copy those URLs from the
Render dashboard after deployment.

If Render reports that either service name is unavailable, change that service
name in `render.yaml` and update the matching `name` in the other service's
`fromService` reference.

### Existing Render Services

Changing names in `render.yaml` does not safely rename services that were
already created under different names. It can cause Render to propose creating
additional services.

For an existing deployment, choose one approach:

1. Keep the existing services and set their environment variables manually:
   - Backend `FRONTEND_URL` = the complete HTTPS frontend URL
   - Frontend `NEXT_PUBLIC_API_BASE_URL` = the complete HTTPS API URL
2. Or suspend/delete the old Render services and create a fresh Blueprint from
   the updated `render.yaml`.

After changing either environment variable, redeploy the affected service. The
frontend variable is embedded during `npm run build`, so the frontend must be
rebuilt rather than only restarted.

## 4. Verify The Deployment

Open these URLs in order:

1. `<API_URL>/health`
2. `<API_URL>/ready`
3. `<FRONTEND_URL>`

`/health` should return `{"status":"ok"}`. `/ready` should report that AI and
data are ready. Then register/sign in, create a subject session, upload a small
PDF, ask a question, refresh the page, and confirm the session and conversation
remain.

For a public deployment, keep backend `AUTH_REGISTRATION_ENABLED=true`. For a
private deployment, set it to `false` after creating your own account and
redeploy the backend.

If the frontend opens but API requests fail:

1. Check the frontend `NEXT_PUBLIC_API_BASE_URL`.
2. Check the backend `FRONTEND_URL`.
3. Confirm both values point to the current services.
4. Redeploy the backend and rebuild the frontend.

## Free-Tier Behavior

- The Render API sleeps after 15 minutes without traffic. The first request
  after sleep can take about a minute.
- The frontend is a static site and remains available through Render's CDN.
- Render's free filesystem is temporary. Original uploaded files can disappear
  after restarts, but extracted document text, vectors, sessions, and chats are
  stored in Neon and remain available.
- This version does not provide an original-file download feature, so temporary
  source-file storage does not break its current study workflows.
- Neon Free currently provides limited compute, storage, and transfer. This is
  appropriate for a small personal deployment, not a large public user base.
- Free services do not provide production uptime guarantees or durable backups.

## Custom Domain

A custom domain is optional and the domain itself is not usually free. If one is
added later:

1. Attach it to the Render static site.
2. Change backend `FRONTEND_URL` to the exact HTTPS frontend origin.
3. Redeploy the backend.

Keep `AI_API_KEY`, database credentials, and all provider configuration on the
backend service only. Never create a `NEXT_PUBLIC_` variable containing a
private credential.

## Authentication Settings

Use these backend settings for a public Render deployment because the frontend
and API are served from HTTPS public origins:

```dotenv
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=none
AUTH_REGISTRATION_ENABLED=true
```

With this setting, visitors can register, but they must sign in before using
documents, chat, study sessions, or study tools. Their data is scoped to their
own account.

For local development over HTTP, use:

```dotenv
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
```

If registration is disabled before any account exists, no one can sign in until
registration is enabled again or a user is inserted directly into the database.
