# Overwatch — Deployment Runbook

**Status:** Active. Single-user private deploy (email-whitelist gated).
**Stack:** Railway (backend + SQLite volume) + the Android app in `mobile/` (ADR-0024).
**Target time:** ~3-4 hours end-to-end the first time.

This runbook is the source of truth for "how is Overwatch deployed." If you ever forget how a wire is connected, look here first.

---

## 0. The end state

```
   Overwatch Android app (mobile/, Expo build)
                  │   Authorization: Bearer <jwt>
                  ▼
   https://overwatch-ai-production.up.railway.app   (Railway — backend)
                  │
        ┌─────────┼─────────────────┐
        ▼         ▼                 ▼
     LLM APIs  Google OAuth   SQLite on Railway volume
                                    (/data/overwatch.db)
```

One running service. One SQLite file. Reminders fire on the phone, not the server.

---

## 1. Prerequisites

Before starting, make sure you have:

- [ ] **GitHub repo** for Overwatch (already done — `Tanmay-Hatkar/overwatch-ai`)
- [ ] **Google Cloud Console** project with OAuth Client ID + Secret (already done — you have `credentials.json`)
- [ ] **Groq account** at https://console.groq.com (free) → generate an API key
- [ ] **Railway account** at https://railway.com → sign in with GitHub (recommended)

If any are missing, stop and create them before proceeding.

---

## 2. Pre-deploy local check

Confirm the latest production-readiness code passes tests on your machine:

```bash
cd backend && pip install -e ".[dev]" && python -m pytest -q
cd ../mobile && npm ci && npm test && npm run lint
```

Everything should pass (the same checks CI runs).

---

## 3. Deploy the backend to Railway

### 3.1 Create the project

1. Go to https://railway.com → **+ New Project** → **Deploy from GitHub repo**
2. Authorize Railway to read the `overwatch-ai` repo
3. Select the repo. Railway will autodetect the Python project.
4. **Set the root directory to `backend`** in the service settings (top-right gear icon → Settings → Source → Root Directory). This tells Railway to build from `backend/` not the repo root.

### 3.2 Add a persistent volume for SQLite

1. In your Railway service, click **+ New** → **Volume**
2. Name: `overwatch-data`
3. Mount path: `/data`
4. Size: 1 GB (way more than we need; can shrink later)

### 3.3 Configure environment variables

Click **Variables** and add each of these (raw values, no quotes):

```
# Auth (from your existing credentials.json + a fresh secret)
SESSION_SECRET=<run: python -c "import secrets; print(secrets.token_urlsafe(48))">
GOOGLE_CLIENT_ID=<from credentials.json>
GOOGLE_CLIENT_SECRET=<from credentials.json>
ALLOWED_GOOGLE_EMAILS=tanmay.hats@gmail.com

# LLM (Groq is free; OpenAI optional)
GROQ_API_KEY=<from console.groq.com>
OPENAI_API_KEY=<optional, set a $5 cap in OpenAI dashboard if used>

# Production toggles
ENVIRONMENT=production
LOG_LEVEL=INFO
DATABASE_PATH=/data/overwatch.db

# URLs — fill these in AFTER first deploy generates them (see section 3.5)
BACKEND_URL=<https://...up.railway.app, fill in section 3.5>
# CORS_ORIGINS is not needed in production: the native app isn't subject to CORS.
```

### 3.4 First deploy

1. Railway will start building automatically the first time you connect the repo. Watch the build logs — first build takes ~3-5 minutes.
2. If the build fails: re-read the error. Most common: wrong root directory (verify "backend" is set in Settings → Source).
3. Once deployed, the **Deploy logs** should end with something like `INFO: Uvicorn running on http://0.0.0.0:XXXX`.

### 3.5 Generate the public URL + plug it back in

1. Click **Settings** → **Networking** → **Generate Domain**. Railway gives you something like `overwatch-production-abc123.up.railway.app`.
2. Copy that URL.
3. Go back to **Variables** and set:
   ```
   BACKEND_URL=https://overwatch-production-abc123.up.railway.app
   ```
4. Railway will redeploy automatically.
5. Hit `https://<your-railway-url>/health` in a browser. Should see `{"status":"ok"}`.

If you see `{"status":"ok"}`, **the backend is live.**

---

## 4. Point the app at the backend

Set `expo.extra.apiBaseUrl` in `mobile/app.json` to the Railway URL from §3.5, then build the app (`cd mobile && npx expo run:android`, or an EAS build). The app reads this at build time.

---

## 5. Update Google Cloud OAuth redirect URI

This is **the most common deploy bug.** The OAuth callback URL must EXACTLY match what's registered in GCP.

1. Go to https://console.cloud.google.com/apis/credentials
2. Click your OAuth 2.0 Client ID (the same one in `credentials.json`)
3. Under **Authorized redirect URIs**, click **+ ADD URI** and add:
   ```
   https://<your-railway-url>/auth/google/callback
   ```
   Example: `https://overwatch-production-abc123.up.railway.app/auth/google/callback`
4. Click **Save**.

Keep the existing `http://localhost:8000/auth/google/callback` entry too so local dev still works.

---

## 6. Smoke test

1. Open the Overwatch app on your phone
2. Tap **Sign in with Google** → the system browser opens Google's consent screen
3. After consenting, the browser hands back to the app (`overwatch://auth`) and you land on the Todos screen
4. In chat, type "remind me to test the deploy in 2 minutes"
5. Close the app. Within ~2 minutes you should get the reminder notification (scheduled on the device). Ignore it, and it should escalate to the full-screen ring.

**If anything breaks here, see §8 Troubleshooting.**

---

## 7. Re-deploy procedure (for future updates)

Railway auto-deploys the backend on every push to `main`. App changes need a new build (`npx expo run:android` or EAS). The loop is:

```powershell
# Make changes locally
cd c:\Tanmay\Self-Study\overwatch
# ... edit files ...

# Verify tests pass
cd backend && python -m pytest -q

# Commit and push
cd ..
git add .
git commit -m "feat: <what you changed>"
git push

# Railway builds automatically — watch its dashboard for a green check.
```

If a deploy fails, Railway keeps the previous version running. Fix the bug, push again.

---

## 8. Troubleshooting

### Backend: 500 on every request

- Check Railway **Deploy logs** for a Python traceback
- Most common: missing env var (a Pydantic Settings validation error appears at startup)
- Verify SESSION_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET are all set

### Sign-in: redirect_uri_mismatch

- Google's error page says `Error 400: redirect_uri_mismatch`
- The URL Google saw doesn't match any URI registered in GCP
- Copy the exact "Request details" URL Google shows and add it as an Authorized redirect URI in GCP

### Sign-in: the app shows `email_not_allowed`

- The email you used isn't in `ALLOWED_GOOGLE_EMAILS`
- Either add it (in Railway env vars), or sign in with the right account

### Reminders don't arrive

- Reminders are scheduled **on the phone** (expo-notifications), not by the server
- Check Android notification permission for Overwatch, and "Alarms & reminders" (exact alarms) permission
- Battery optimisation can delay notifications: set Overwatch to "Unrestricted"
- Reopen the app once: it reconciles scheduled reminders against the current commitment list

### Calendar events not showing

- Expected: there is no way to connect a calendar from the mobile app yet (ADR-0024)
- Briefings work fine without it — calendar is background context only (ADR-0022)

### "Database is locked" errors in Railway logs

- SQLite + concurrent writes can lock. For single-user this should be rare.
- If it happens often, that's a signal to migrate to Postgres (planned for slice 13)

### Railway free credits used up

- Railway Hobby plan is $5/mo + usage above $5
- If your bill creeps past $5, check the Metrics tab — usually it's memory
- For a single-user app, memory should stay under 200MB easily

---

## 9. Cost monitoring checklist

- [ ] Set OpenAI dashboard monthly budget cap to $5 (https://platform.openai.com/account/limits)
- [ ] Enable Railway billing alerts (Settings → Notifications → Usage limits)
- [ ] Quarterly: check GCP Console for any unexpected API usage spikes

---

## 10. Tearing it down (if you ever want to)

If you stop using Overwatch:

1. **Railway:** Settings → Danger → Delete Service. Volume gets deleted too (download `overwatch.db` first if you want to keep data).
2. **GCP:** Remove the Authorized redirect URIs (optional but tidy).
3. **Groq:** No action needed — free tier auto-expires unused keys.

---

## 11. References

- [Railway docs — Python deploys](https://docs.railway.com/guides/python)
- [Google OAuth — Authorized redirect URIs](https://developers.google.com/identity/protocols/oauth2/web-server#redirect_uri)
- ADR-0009 — auth design; ADR-0024 — mobile-only client (bearer auth)
- ADR-0010 (on `feature/slice-12-multi-tenancy` branch) — multi-tenancy design
- `docs/HANDBOOK.md` — project bird's-eye view
