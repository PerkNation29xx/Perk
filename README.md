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

## Environment profiles
- Local development uses `.env.development.local`
- Production-mirror access uses `.env.production.local`
- If `PERKNATION_ENV_FILE` is not set, the backend falls back to `.env`
- Local watchdog/HTTPS scripts automatically prefer `.env.development.local`, so you do not have to hand-edit env files when testing
- To verify what the backend will use right now, run `./scripts/show_active_env.sh`

## Local run (without Docker)
1. `cd /Users/nation/Documents/New project/PerkNationBackend`
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.development.example .env.development.local`
5. Run local dev:
   - `PERKNATION_ENV_FILE=.env.development.local uvicorn app.main:app --reload`
   - or use the local scripts below, which already do this automatically

## Local HTTPS (self-signed cert)
To avoid transmitting form data over plaintext locally:

1. `cd /Users/nation/Documents/New project/PerkNationBackend`
2. `./scripts/run_local_https.sh`
3. Open [https://127.0.0.1:8443/](https://127.0.0.1:8443/)

Optional (macOS trust install):
- `./scripts/trust_local_cert_macos.sh`

## Production-mirror config
If you want a local profile that mirrors production/Supabase, store it in `/Users/nation/Documents/New project/PerkNationBackend/.env.production.local`.

Use `/Users/nation/Documents/New project/PerkNationBackend/.env.production.example` as the template.

## Connect To Supabase Postgres (Live DB)
If you want the backend to use Supabase as the database, set these in `/Users/nation/Documents/New project/PerkNationBackend/.env.production.local`:

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

## Stripe test/live toggle
Use dual Stripe keys so you can switch between testing and live charges without re-entering keys.

Required env vars:
- `STRIPE_MODE=test` or `STRIPE_MODE=live`
- `STRIPE_SECRET_KEY_TEST`, `STRIPE_PUBLISHABLE_KEY_TEST`
- `STRIPE_SECRET_KEY_LIVE`, `STRIPE_PUBLISHABLE_KEY_LIVE`
- Optional webhooks:
  - `STRIPE_WEBHOOK_SECRET_TEST`
  - `STRIPE_WEBHOOK_SECRET_LIVE`

Backward compatibility:
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` still work as fallback.

Notes:
- Stripe mode is recorded on checkout rows and visible in Admin -> Orders.
- Webhook verification tries the configured mode first, then the other mode, then legacy secret.

## AI assistant provider (local or public)
The app AI chat goes through the backend (`POST /v1/ai/chat`).

Use local Ollama:
- `AI_ENABLED=true`
- `AI_PROVIDER=ollama`
- `OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=qwen3:30b`

Use Ollama via internal gateway (for shared Spark model hosting):
- `AI_ENABLED=true`
- `AI_PROVIDER=ollama`
- `OLLAMA_BASE_URL=http://47.51.26.74:8088`
- `OLLAMA_MODEL=nemotron-mini:latest`
- `OLLAMA_API_KEY=<gateway-api-key>`
- `OLLAMA_BYPASS_TOKEN=<gateway-bypass-token>`
- `OLLAMA_HOST_HEADER=llm.api.local`

Use hosted/public model:
- `AI_ENABLED=true`
- `AI_PROVIDER=openai`
- `OPENAI_API_KEY=<your-key>`
- `OPENAI_MODEL=gpt-4.1-mini`

Notes:
- The backend also supports OpenAI-compatible endpoints via `OPENAI_BASE_URL`.
- Keep AI provider keys on the backend only (never in mobile app code).

## LA restaurant knowledge for AI
- The backend includes a curated LA-area restaurant knowledge dataset used by AI chat.
- Startup seed toggle:
  - `SEED_RESTAURANT_KNOWLEDGE_DATA=true`
- Manual refresh:
  - `PYTHONPATH=. .venv/bin/python scripts/seed_la_restaurant_knowledge.py --refresh`
- Bulk import your own large dataset:
  - `PYTHONPATH=. .venv/bin/python scripts/import_restaurant_knowledge_csv.py ./restaurants.csv`
- Public search endpoint:
  - `GET /v1/restaurants/search?q=best+sushi+in+pasadena`

## If localhost still does not work
1. Verify the API is running: `curl http://127.0.0.1:8000/v1/health`
2. If using iOS Simulator, use `http://127.0.0.1:8000`
3. If using a physical iPhone, use your Mac LAN IP, e.g. `http://192.168.1.23:8000` (not `localhost`)

## Refresh local DB from production
To repopulate the local development DB from the production-shaped profile:

1. Ensure `/Users/nation/Documents/New project/PerkNationBackend/.env.production.local` points at Supabase/prod
2. Ensure `/Users/nation/Documents/New project/PerkNationBackend/.env.development.local` points at your local SQLite dev DB
3. Run:
   - `python scripts/refresh_local_from_production.py`

The script backs up the local SQLite DB before overwriting it.

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
- Restaurants: `/v1/restaurants/search`
- Website forms: `POST /v1/web/forms/{member|merchant|contact}` (`guest` remains as a backward-compatible alias)
- SMS webhooks: `POST /v1/sms/inbound`, `POST /v1/sms/status`

## Website form backup mirroring
- Each public website form submission writes to your primary DB (Supabase Postgres/local DB).
- Submissions are also mirrored to a local backup DB when enabled:
  - `FORMS_BACKUP_ENABLED=true`
  - `FORMS_BACKUP_DATABASE_URL=sqlite:///./perknation_forms_backup.db`
- One-time full copy (primary -> local backup):
  - `python -m scripts.sync_web_forms_to_backup`

## Contact form inbox + email forwarding
- Contact form submissions are stored in `web_lead_submissions` with `form_type='contact'`.
- Admin-only API inbox:
  - `GET /v1/admin/contact-inbox` (requires admin bearer token)
- Optional support email forwarding for each new contact submission:
  - `CONTACT_EMAIL_FORWARDING_ENABLED=true`
  - `CONTACT_FORM_NOTIFY_EMAIL=perknation29@icloud.com`
  - SMTP vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`, `SMTP_USE_SSL`

## SMS messaging (welcome + customer communications)
- SMS uses Twilio when enabled:
  - `SMS_ENABLED=true`
  - `SMS_PROVIDER=twilio`
  - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
  - `TWILIO_MESSAGING_SERVICE_SID_PERKNATION`
  - `TWILIO_MESSAGING_SERVICE_SID_HQ` (kept separate for The HQ)
- Optional webhook/delivery settings:
  - `TWILIO_STATUS_CALLBACK_URL`
  - `SMS_VALIDATE_WEBHOOK_SIGNATURE=true`
  - `SMS_WEBHOOK_BASE_URL=https://api.perknation.net` (if behind a proxy)
- User profile now stores SMS consent and delivery state:
  - `sms_opt_in`, `sms_opt_in_at`, `sms_opt_in_source`, `sms_opt_out_at`, `sms_welcome_sent_at`, `sms_last_error`
- Twilio webhook endpoints:
  - `POST /v1/sms/inbound` (STOP/START/HELP handling)
  - `POST /v1/sms/status` (delivery status callback)
- In Twilio Messaging Service settings:
  - Set incoming message webhook URL to `/v1/sms/inbound`
  - Set delivery status callback URL to `/v1/sms/status`

## Seed LA citywide offers (includes Marina del Rey)
To test geolocation/radius behavior with dense data:

1. `cd /Users/nation/Documents/New project/PerkNationBackend`
2. `source .venv/bin/activate`
3. `python scripts/seed_la_citywide_offers.py`

This creates/updates:
- 10 merchants
- 26 LA neighborhoods
- 260 active location-bound offers (idempotent)

## Playwright E2E setup (Python)
Use this to run browser-based smoke tests locally.

1. `cd /Users/nation/Documents/New project/PerkNationBackend`
2. `source .venv/bin/activate`
3. `pip install -r requirements-dev.txt`
4. `python -m playwright install chromium`
5. Run tests:
   - `python scripts/check_site_flows.py`
   - `python scripts/check_site_links.py`
   - `pytest tests/e2e`

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
