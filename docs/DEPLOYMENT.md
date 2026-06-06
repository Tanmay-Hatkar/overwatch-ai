# Overwatch — Deployment Runbook

**Status:** Active. Single-user private deploy (email-whitelist gated).
**Stack:** Railway (backend + SQLite volume) + Vercel (frontend static site).
**Target time:** ~3-4 hours end-to-end the first time.

This runbook is the source of truth for "how is Overwatch deployed." If you ever forget how a wire is connected, look here first.

---

## 0. The end state

```
   Browser / installed PWA on your phone
                  │
                  ▼
   https://overwatch.vercel.app          (Vercel — frontend)
                  │
                  ▼
   https://overwatch.up.railway.app      (Railway — backend container)
                  │
        ┌─────────┼─────────────────┐
        ▼         ▼                 ▼
     Groq API  Google APIs    SQLite on Railway volume
                                    (/data/overwatch.db)
```

Two running services. One SQLite file. Three external APIs.

---

## 1. Prerequisites

Before starting, make sure you have:

- [ ] **GitHub repo** for Overwatch (already done — `Tanmay-Hatkar/overwatch-ai`)
- [ ] **Google Cloud Console** project with OAuth Client ID + Secret (already done — you have `credentials.json`)
- [ ] **Groq account** at https://console.groq.com (free) → generate an API key
- [ ] **Railway account** at https://railway.com → sign in with GitHub (recommended)
- [ ] **Vercel account** at https://vercel.com → sign in with GitHub (recommended)
- [ ] **VAPID keys** generated (already in your local `.env`)

If any are missing, stop and create them before proceeding.

---

## 2. Pre-deploy local check

Confirm the latest production-readiness code passes tests on your machine:

```powershell
cd c:\Tanmay\Self-Study\overwatch\backend
pip install -e ".[dev]"
python -m pytest -q
```

Expect **194 passed**.

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

# Web Push (copy from local .env)
VAPID_PUBLIC_KEY=<from local .env>
VAPID_PRIVATE_KEY=<from local .env>
VAPID_SUBJECT=mailto:tanmay.hats@gmail.com

# LLM (Groq is free; OpenAI optional)
GROQ_API_KEY=<from console.groq.com>
OPENAI_API_KEY=<optional, set a $5 cap in OpenAI dashboard if used>

# Production toggles
ENVIRONMENT=production
LOG_LEVEL=INFO
DATABASE_PATH=/data/overwatch.db

# URLs — fill these in AFTER first deploy generates them (see section 3.5)
BACKEND_URL=<https://...up.railway.app, fill in section 3.5>
FRONTEND_URL=<https://...vercel.app, fill in section 4.4>
CORS_ORIGINS=<same as FRONTEND_URL, fill in section 4.4>
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

If you see `{"status":"ok"}`, **the backend is live.** Move on to Vercel.

---

## 4. Deploy the frontend to Vercel

### 4.1 Create the project

1. Go to https://vercel.com → **Add New** → **Project**
2. Import the `overwatch-ai` repo (authorize Vercel if not already)
3. **Root Directory:** set to `frontend` (Vercel asks during setup)
4. Framework Preset: Vite (auto-detected)
5. Don't deploy yet — first set env vars (next step)

### 4.2 Configure environment variables

Click **Environment Variables** and add:

```
VITE_API_BASE_URL=<your Railway URL from section 3.5>
```

Example: `VITE_API_BASE_URL=https://overwatch-production-abc123.up.railway.app`

Set for: **Production, Preview, Development** (check all three).

### 4.3 Deploy

Click **Deploy**. First build takes ~1-2 min.

### 4.4 Get the Vercel URL + wire it back to Railway

1. Vercel gives you a URL like `overwatch-frontend-xyz.vercel.app`.
2. Go back to Railway → **Variables** and set:
   ```
   FRONTEND_URL=https://overwatch-frontend-xyz.vercel.app
   CORS_ORIGINS=https://overwatch-frontend-xyz.vercel.app
   ```
3. Railway redeploys.

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

1. Open `https://<your-vercel-url>` in a desktop browser
2. You should see the orange "Overwatch" login screen
3. Click **Sign in with Google**
4. Google's consent screen → click Continue
5. You should land back on the Overwatch home page with your name + picture in the header
6. Type "remind me to test the deploy in 1 minute" in the ChatBar
7. After ~1 minute, you should receive a Web Push notification (if you granted permission)

**If anything breaks here, see §9 Troubleshooting.**

---

## 7. Install the PWA on your phone

### iOS (Safari)

1. Open `https://<your-vercel-url>` in Safari (not Chrome)
2. Tap the Share icon (square with up-arrow)
3. Scroll down → **Add to Home Screen**
4. Tap **Add**
5. Open the new Overwatch icon from your home screen — opens fullscreen, no browser bar

### Android (Chrome)

1. Open `https://<your-vercel-url>` in Chrome
2. Tap the 3-dot menu (top-right)
3. **Add to Home screen** or **Install app**
4. Confirm
5. Opens like a native app from the home screen

---

## 8. Re-deploy procedure (for future updates)

Both Railway and Vercel auto-deploy on every push to `main`. So the loop is:

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

# Railway + Vercel both build automatically.
# Watch their dashboards for green checkmarks.
```

If a deploy fails, both platforms keep the previous version running. Fix the bug, push again.

---

## 9. Troubleshooting

### Backend: 500 on every request

- Check Railway **Deploy logs** for a Python traceback
- Most common: missing env var (a Pydantic Settings validation error appears at startup)
- Verify SESSION_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET are all set

### Frontend: Blank page on Vercel

- Open browser devtools → Network tab → reload
- If `index.html` loads but `assets/index-XXX.js` 404s, build failed silently → check Vercel build logs
- If JS loads but API calls fail with CORS errors → check `CORS_ORIGINS` matches your Vercel URL EXACTLY (no trailing slash)

### Sign-in: redirect_uri_mismatch

- Google's error page says `Error 400: redirect_uri_mismatch`
- The URL Google saw doesn't match any URI registered in GCP
- Copy the exact "Request details" URL Google shows and add it as an Authorized redirect URI in GCP

### Sign-in: redirects to home with `?auth_error=email_not_allowed`

- The email you used isn't in `ALLOWED_GOOGLE_EMAILS`
- Either add it (in Railway env vars), or sign in with the right account

### Push notifications don't arrive

- Did you grant notification permission? Check site settings
- iOS: works only if installed as PWA (Add to Home Screen), iOS 16.4+
- Check Railway logs: ReminderScheduler should log a "broadcasting push" line at the due time
- Common issue: VAPID public key in env vars must match what the service worker subscribed with. If you regenerated VAPID keys after subscribing, unsubscribe + re-subscribe in the UI.

### Calendar events not showing

- Calendar isn't auto-configured per-user yet (that's slice 12)
- For now: the deployed instance has no Google Calendar access
- Workaround: just don't use calendar features; commitments/chat work fine

### "Database is locked" errors in Railway logs

- SQLite + concurrent writes can lock. For single-user this should be rare.
- If it happens often, that's a signal to migrate to Postgres (planned for slice 13)

### Railway free credits used up

- Railway Hobby plan is $5/mo + usage above $5
- If your bill creeps past $5, check the Metrics tab — usually it's memory
- For a single-user app, memory should stay under 200MB easily

---

## 10. Cost monitoring checklist

- [ ] Set OpenAI dashboard monthly budget cap to $5 (https://platform.openai.com/account/limits)
- [ ] Enable Railway billing alerts (Settings → Notifications → Usage limits)
- [ ] Watch Vercel Hobby tier limits (100GB bandwidth/mo — you'll never hit this)
- [ ] Quarterly: check GCP Console for any unexpected API usage spikes

---

## 11. Tearing it down (if you ever want to)

If you stop using Overwatch:

1. **Railway:** Settings → Danger → Delete Service. Volume gets deleted too (download `overwatch.db` first if you want to keep data).
2. **Vercel:** Project Settings → Delete. Domain becomes available for re-use.
3. **GCP:** Remove the Authorized redirect URIs (optional but tidy).
4. **Groq:** No action needed — free tier auto-expires unused keys.

---

## 12. References

- [Railway docs — Python deploys](https://docs.railway.com/guides/python)
- [Vercel docs — Vite framework](https://vercel.com/docs/frameworks/vite)
- [Google OAuth — Authorized redirect URIs](https://developers.google.com/identity/protocols/oauth2/web-server#redirect_uri)
- [Web Push protocol](https://developers.google.com/web/fundamentals/push-notifications)
- ADR-0009 — auth design
- ADR-0010 (on `feature/slice-12-multi-tenancy` branch) — multi-tenancy design
- `docs/HANDBOOK.md` — project bird's-eye view
