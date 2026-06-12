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

The current application also has no login system or per-user data isolation.
Anyone who can reach the public URL can use the workspace and may be able to
view or delete its content. Do not upload private material or advertise the URL
to untrusted users until authentication and authorization are implemented.

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

5. Apply the Blueprint and wait for both services to finish deploying.

Render assigns public addresses to both services. Copy those URLs from the
Render dashboard after deployment.

If Render reports that either service name is unavailable, change that service
name in `render.yaml` and update the matching `name` in the other service's
`fromService` reference.

## 4. Verify The Deployment

Open these URLs in order:

1. `<API_URL>/health`
2. `<API_URL>/ready`
3. `<FRONTEND_URL>`

`/health` should return `{"status":"ok"}`. `/ready` should report that AI and
data are ready. Then create a subject session, upload a small PDF, ask a
question, refresh the page, and confirm the session and conversation remain.

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
