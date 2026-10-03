# Ads Optimizer — SaaS

Multi-tenant Google Ads auto-optimizer. Each client connects their own
Google Ads account once (OAuth); after that, a daily job automatically:

- Adds wasteful search terms as negative keywords
- Pauses keywords/ads that spend money with zero conversions
- **Never touches budget or bidding** — emails + shows a dashboard
  recommendation instead
- Sends a weekly report per connected account

No third-party data platform in the loop — this talks to the official
Google Ads API directly.

## Stack

- **Backend:** FastAPI + PostgreSQL + Google's `google-ads` Python library
- **Frontend:** React + TypeScript + Vite
- **Scheduler:** APScheduler, in-process with the backend

## Why this is more work than a single-account tool

Because multiple clients each connect their *own* Google Ads account, this
needs: its own login system (separate from each client's Google login),
per-client encrypted OAuth refresh token storage, and a database — none
of which a single-account personal script needs. That's the complexity
trade you're taking on by going multi-tenant.

## 1. One-time setup (you, the operator)

### a) Google Cloud OAuth credentials

These are **different** from the Google Ads developer token — this is
what lets *your clients* grant your app access to *their* Google Ads account.

1. Go to https://console.cloud.google.com, create a project
2. APIs & Services → OAuth consent screen → configure it (External
   user type unless this is only ever for people inside your own Google
   Workspace org)
3. APIs & Services → Credentials → Create Credentials → OAuth
   client ID → Web application
4. Add an Authorized redirect URI: `http://localhost:8000/oauth/google/callback`
   (update this to your real domain before going to production)
5. Copy the Client ID and Client Secret into `backend/.env`

Your OAuth consent screen will show "unverified app" warnings to clients
until Google reviews it (needed once you have real external users) —
expect to submit for verification before launching publicly.

### b) Google Ads developer token (you already have this in progress)

From your MCC: **Admin → API Center**. Needs Basic Access approval for
production accounts (see your earlier research on this — Explorer
Access may now streamline the first step).

### c) Database

```bash
# Local Postgres via Docker, or use any Postgres you already have
docker run -d --name ads-saas-db -e POSTGRES_PASSWORD=postgres \\
  -e POSTGRES_DB=ads_saas -p 5432:5432 postgres:16
```

### d) Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Generate secrets:
python3 -c "import secrets; print(secrets.token_hex(32))"               # -> SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # -> FERNET_KEY
# Fill in .env: the above two, Google OAuth client id/secret, Ads developer
# token, your MCC id, and SMTP credentials.

uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/health — should return `{"status": "ok"}`.
Tables are auto-created on first startup (swap for Alembic migrations
before production — `alembic/` is scaffolded but empty).

### e) Frontend

```bash
cd frontend
npm install
cp .env.example .env   # points VITE_API_BASE at your backend
npm run dev
```

Visit http://localhost:5173, sign up for an account, then click
**"Connect Google Ads account."**

## 2. The connect flow, end to end

1. Client signs up / logs into your dashboard (your own auth, JWT-based)
2. Clicks "Connect Google Ads" → redirected to Google's consent screen
3. Approves → Google redirects back with a refresh token
4. If that login can access more than one Google Ads account, the client
   picks which one on a "Finish connecting" screen and sets a notify email
5. Done — the backend stores the refresh token (encrypted) and the daily
   job picks this account up automatically from then on

## 3. Running the daily job

APScheduler starts automatically with the backend (see `core/scheduler.py`,
default 06:00 UTC for all active accounts). For anything beyond a handful of
early clients, replace this with Celery Beat + workers so one slow/stuck
account can't delay the rest — the run logic in `core/run_account.py` is
already decoupled from *how* it gets called, so that swap doesn't touch the
rule engine or safety layer.

Each client can also click **"Run now"** in the dashboard to test without
waiting for the schedule — it still respects their own dry-run setting.

## 4. Safety design (three independent layers)

1. **`core/google_ads_client.py`** structurally cannot write budget or bid
   fields — no method in that file accepts or sets `budget_micros`,
   `cpc_bid_micros`, `target_cpa`, `target_roas`, or any bidding strategy
   field. The capability doesn't exist in the code.
2. **`core/executor.py`** is a second, independent allowlist of which client
   methods are even callable from the rule engine's output.
3. **Per-account `max_actions_per_run`** circuit breaker, and **dry-run
   mode** (default on for every newly-connected account) so nothing live
   happens until the operator or client flips it off deliberately.

Budget/bidding opportunities are always a `Recommendation` row shown in the
dashboard and emailed — a human applies them in Google Ads and marks
them "applied."

## 5. What's deliberately left out of this first version

- **Alembic migrations** — using `create_all` for now; add migrations
  before this holds real client data you can't afford to lose on a schema change
- **Per-account rule thresholds** — currently global constants in
  `core/rule_engine.py`; move to DB columns per account once you have
  several clients with different traffic volumes
- **Billing/subscriptions** — nothing here charges clients; add Stripe
  when you're ready to monetize
- **Celery/worker queue** — APScheduler in-process is fine for the first
  cohort; swap when you have enough accounts that a slow one could delay others
- **Google OAuth consent screen verification** — required before you can
  onboard clients outside a Google Workspace test-user allowlist

## 6. A note on the sandbox this was built in

This project's Python and TypeScript were written and syntax-checked here
(`py_compile` clean on every backend file, `tsc --noEmit` clean apart from
expected "module not installed" errors that resolve once you `pip install`
/ `npm install` on your own machine). Network access to PyPI/npm was
blocked in this particular environment, so the actual `pip install` /
`npm install` / live server run has not happened yet — do that first on
your machine and work through any dependency-version hiccups before
connecting a real Google Ads account.
