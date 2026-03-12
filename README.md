# PerkNationBackend

Production-oriented backend starter for the PerkNation iPhone app MVP.

## What is included
- FastAPI REST API with OpenAPI docs (`/docs`)
- SQLAlchemy data model for core launch entities:
  - users (consumer/merchant/admin)
  - merchant profiles + locations
  - offers + activations
  - transactions + rewards ledger
  - support tickets + disputes
  - admin audit logs
- JWT authentication + role-based access control
- Docker Compose stack for API + PostgreSQL
- Automatic table creation + seed data on first boot

## Quick start (Docker)
1. `cd /Users/nation/Documents/New project/PerkNationBackend`
2. `cp .env.example .env`
3. Update `JWT_SECRET_KEY` in `.env`
4. `docker compose up --build`
5. Open docs at [http://localhost:8000/docs](http://localhost:8000/docs)

## Local run (without Docker)
1. `cd /Users/nation/Documents/New project/PerkNationBackend`
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.example .env`
5. Keep SQLite default in `.env` (`sqlite:///./perknation.db`) unless you already run Postgres
6. `uvicorn app.main:app --reload`

## Local HTTPS (self-signed cert)
To avoid transmitting form data over plaintext locally:

1. `cd /Users/nation/Documents/New project/PerkNationBackend`
2. `./scripts/run_local_https.sh`
3. Open [https://127.0.0.1:8443/](https://127.0.0.1:8443/)

Optional (macOS trust install):
- `./scripts/trust_local_cert_macos.sh`

## Connect To Supabase Postgres (Live DB)
If you want the backend to use Supabase as the database (so your iOS app uses a live DB), set these in `/Users/nation/Documents/New project/PerkNationBackend/.env`:

- Preferred for cloud hosts (Render): set `DATABASE_URL` to Supabase **pooler** URL (port `6543`, ssl required).
- Or use direct host vars:
  - `DATABASE_HOST=db.<your-project-ref>.supabase.co`
  - `DATABASE_PORT=5432`
  - `DATABASE_NAME=postgres`
  - `DATABASE_USER=postgres`
  - `DATABASE_PASSWORD=<your-db-password>`
  - `DATABASE_SSLMODE=require`

Notes:
- Using the discrete vars above avoids URL-encoding problems if your password contains characters like `#` or `@`.
- If `DATABASE_URL` is set (non-default), it takes precedence over discrete `DATABASE_*` vars.
- First run will `create_all()` tables in your Supabase database. For a real production setup, use Alembic migrations instead.
- If you don't want demo data in Supabase, set `SEED_DEFAULT_DATA=false`.

## Use Supabase Auth (Recommended)
Production-style setup:
- The iOS app signs up / signs in directly with Supabase Auth (email + password).
- The iOS app sends the Supabase access token to this backend as `Authorization: Bearer <token>`.
- The backend validates the token by calling `GET /auth/v1/user` on Supabase and creates/links a local user profile row in `public.users`.

Backend `.env` requirements:
- `SUPABASE_URL=https://<your-project-ref>.supabase.co`
- `SUPABASE_ANON_KEY=sb_publishable_...`

Notes:
- Do not put any Supabase service-role keys in the iOS app.
- Email verification is handled by Supabase (confirmation email). The MVP iOS app currently expects you to confirm via email, then log in.

## If localhost still does not work
1. Verify the API is running: `curl http://127.0.0.1:8000/v1/health`
2. If using iOS Simulator, use `http://127.0.0.1:8000`
3. If using a physical iPhone, use your Mac LAN IP, e.g. `http://192.168.1.23:8000` (not `localhost`)

## LAN access (same Wi-Fi/network)
- Ensure the API is bound to all interfaces (`0.0.0.0`) and healthy.
- Print shareable links:
  - `./scripts/show_lan_links.sh`
- Start/recover local services if needed:
  - `./scripts/watchdog_services.sh`

## Seeded accounts
- Admin: `admin@perknation.dev` / `AdminPass123!`
- Merchant: `merchant@perknation.dev` / `MerchantPass123!`
- Consumer: `user@perknation.dev` / `UserPass123!`

## Email verification (dev)
- New accounts require email verification before login.
- In local dev, set `DEV_EXPOSE_EMAIL_VERIFICATION_CODE=true` in `.env` to have the API return the verification code.
- Endpoints:
  - `POST /v1/auth/register`
  - `POST /v1/auth/email/verification/request`
  - `POST /v1/auth/email/verify`

## Core endpoints
- Auth: `/v1/auth/register`, `/v1/auth/token`, `/v1/auth/me`
- Consumer: `/v1/consumer/offers`, `/v1/consumer/offers/{offer_id}/activate`, `/v1/consumer/transactions`, `/v1/consumer/rewards`, `/v1/consumer/rewards/redeem`, `/v1/consumer/support/tickets`, `/v1/consumer/disputes`
- Merchant: `/v1/merchant/profile`, `/v1/merchant/locations`, `/v1/merchant/offers`, `/v1/merchant/metrics`
- Admin: `/v1/admin/approvals`, `/v1/admin/approvals/{offer_id}`, `/v1/admin/disputes`, `/v1/admin/rewards/{reward_id}/adjust`, `/v1/admin/disputes/{dispute_id}/resolve`
- Website forms: `POST /v1/web/forms/{guest|merchant|contact}`

## Website form backup mirroring
- Each public website form submission writes to your primary DB (Supabase Postgres/local DB).
- Submissions are also mirrored to a local backup DB when enabled:
  - `FORMS_BACKUP_ENABLED=true`
  - `FORMS_BACKUP_DATABASE_URL=sqlite:///./perknation_forms_backup.db`
- One-time full copy (primary -> local backup):
  - `python -m scripts.sync_web_forms_to_backup`

## Next production steps
- Add Alembic migrations (instead of `create_all`)
- Add Redis queue + workers for settlement windows and delayed reward state transitions
- Replace mock transaction ingestion with a payment rail integration
- Add KYC/KYB integration and compliance webhooks
- Add monitoring, tracing, and rate limiting (API gateway/WAF)

## Public hosting (Render + Supabase)
Use the same Supabase public project details you already run locally.

1. Push this backend folder to GitHub.
2. In Render, create a new **Web Service** from the repo.
3. Render can auto-read `render.yaml` in this folder:
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health: `/v1/health`
4. In Render env vars, set secrets:
   - `DATABASE_HOST`, `DATABASE_PASSWORD`
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY`
   - `JWT_SECRET_KEY` (strong random value)
5. Keep production flags:
   - `SEED_DEFAULT_DATA=false`
   - `DEV_EXPOSE_EMAIL_VERIFICATION_CODE=false`
6. Add custom domains as needed (for example):
   - `www.<your-domain>`
   - `api.<your-domain>` (optional, same service)
7. Optional CI:
   - Add GitHub secret `RENDER_DEPLOY_HOOK_URL`
   - Workflow file: `.github/workflows/deploy-render.yml`
