# Tier 4 Part E — Implementation Plan

## Codebase Findings (pre-plan research)

### 1. Location of resolve functions
- `resolve_email_providers(db, workspace)` → `backend/app/services/providers.py` line ~95
- `resolve_sms_provider(db, workspace)` → `backend/app/services/providers.py` line ~160
- `has_email_provider(db, workspace)` → same file line ~195
- `has_sms_provider(db, workspace)` → same file line ~209
- Called from `backend/app/tasks/notification_tasks.py` (lines 240–254) and from `backend/app/api/notifications.py` (has_email_provider / has_sms_provider at notification-create time)

### 2. `use_platform_providers` on Workspace model
**Yes — it exists.** Field name: `use_platform_providers` (Boolean, default False, server_default 'false').
Defined in `backend/app/models/workspace.py`. Set to True for the default workspace in the migration
`backend/alembic/versions/d4e5f6a7b8c9_provider_credentials_and_workspace_hardening.py`.

### 3. Current provider-precedence logic — BUG
The current logic in `resolve_email_providers` and `resolve_sms_provider`:
```
if workspace is None or workspace.use_platform_providers:
    return platform_providers
# else: return own credentials
```
This is **inverted**: if `use_platform_providers=True`, platform is used. If workspace has own
credentials AND `use_platform_providers=False`, own credentials are used. But there is no
**fallback**: if workspace has own credentials AND `use_platform_providers=True`, platform is
used instead of own credentials — this contradicts the new requirement that "own credentials
always win."

The same inversion affects `has_email_provider` and `has_sms_provider`.

**Required new rule** (Section 0a):
1. If workspace has own active ProviderCredential rows → use ONLY those (regardless of `use_platform_providers`).
2. Else if `workspace.use_platform_providers is True` → use platform (.env) providers.
3. Else → no provider (empty list / None).

### 4. Celery broker/backend config variable names
`backend/app/celery_app.py` uses `settings.redis_url` for BOTH broker and backend:
```python
broker=settings.redis_url,
backend=settings.redis_url,
```
The CI workflow defines `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` as environment
variables, but **celery_app.py does NOT read them** — it reads only `REDIS_URL`.
**docker-compose.yml must use `REDIS_URL` for both broker and backend.**
The separate `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` in the CI env are legacy noise;
do NOT add them to docker-compose service env or root `.env.example`.

### 5. SuppressionCreate schema — already correct
`backend/app/schemas/notification.py` line ~58:
```python
class SuppressionCreate(BaseModel):
    channel: str
    recipient: str
    reason: Literal["opt_out", "bounce"] = "opt_out"
```
The `Literal["opt_out", "bounce"]` constraint **already exists**. No change needed for 0b.

### 6. SuppressionsPage.jsx reason options — needs fix
`frontend/src/pages/settings/SuppressionsPage.jsx` line 14:
```js
const REASON_OPTIONS = ['opt_out', 'bounce', 'complaint', 'manual'];
```
`complaint` and `manual` must be removed. New value: `['opt_out', 'bounce']`.

### 7. Frontend API base URL pattern
`frontend/src/lib/api.js` uses a module-level constant:
```js
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
```
`OverviewPage.jsx` and `ApiKeysPage.jsx` each have their own inline copy of this expression.
All three must be updated to call a new `absoluteApiBase()` helper that reads
`window.__APP_CONFIG__.API_BASE_URL` first.

### 8. Layout.jsx NAV array
`frontend/src/components/Layout.jsx` — the `NAV` array currently has:
`['/', '/notifications', '/templates', '/send', '/bulk', '/settings', '/platform']`.
A `/docs` entry must be added (not restricted to admin or superadmin).

### 9. All env vars from config.py (for docker-compose and root .env.example)
Required env vars (mapped from pydantic field name → env var name):

| Pydantic field             | Env var                    | Notes                              |
|---------------------------|----------------------------|------------------------------------|
| app_name                  | APP_NAME                   |                                    |
| debug                     | DEBUG                      |                                    |
| database_url              | DATABASE_URL               | Required                           |
| redis_url                 | REDIS_URL                  | Required; also Celery broker+backend |
| db_pool_size              | DB_POOL_SIZE               |                                    |
| db_max_overflow           | DB_MAX_OVERFLOW            |                                    |
| db_pool_timeout           | DB_POOL_TIMEOUT            |                                    |
| db_pool_recycle           | DB_POOL_RECYCLE            |                                    |
| celery_queue              | CELERY_QUEUE               |                                    |
| public_base_url           | PUBLIC_BASE_URL            |                                    |
| webhook_secret            | WEBHOOK_SECRET             |                                    |
| webhook_verify            | WEBHOOK_VERIFY             |                                    |
| email_provider_order      | EMAIL_PROVIDER_ORDER       |                                    |
| smtp_host                 | SMTP_HOST                  |                                    |
| smtp_user                 | SMTP_USER                  |                                    |
| smtp_password             | SMTP_PASSWORD              |                                    |
| smtp_from_email           | SMTP_FROM_EMAIL            |                                    |
| smtp_port                 | SMTP_PORT                  |                                    |
| smtp_use_tls              | SMTP_USE_TLS               |                                    |
| brevo_api_key             | BREVO_API_KEY              |                                    |
| brevo_from_email          | BREVO_FROM_EMAIL           |                                    |
| twilio_account_sid        | TWILIO_ACCOUNT_SID         |                                    |
| twilio_auth_token         | TWILIO_AUTH_TOKEN          |                                    |
| twilio_from_number        | TWILIO_FROM_NUMBER         |                                    |
| api_key                   | API_KEY                    | Required                           |
| jwt_secret                | JWT_SECRET                 | Required                           |
| jwt_expire_minutes        | JWT_EXPIRE_MINUTES         |                                    |
| metrics_token             | METRICS_TOKEN              |                                    |
| log_format                | LOG_FORMAT                 |                                    |
| frontend_url              | FRONTEND_URL               |                                    |
| schedule_max_days         | SCHEDULE_MAX_DAYS          |                                    |
| bulk_max_recipients       | BULK_MAX_RECIPIENTS        |                                    |
| max_workspaces_per_user   | MAX_WORKSPACES_PER_USER    |                                    |
| unsubscribe_secret        | UNSUBSCRIBE_SECRET         |                                    |
| webhook_channel_allowed_hosts | WEBHOOK_CHANNEL_ALLOWED_HOSTS |                              |
| signup_mode               | SIGNUP_MODE                |                                    |
| require_email_verification| REQUIRE_EMAIL_VERIFICATION |                                    |
| system_mail_backend       | SYSTEM_MAIL_BACKEND        |                                    |
| frontend_public_url       | FRONTEND_PUBLIC_URL        |                                    |
| encryption_key            | ENCRYPTION_KEY             |                                    |
| allow_private_smtp_hosts  | ALLOW_PRIVATE_SMTP_HOSTS   |                                    |
| trusted_proxy_count       | TRUSTED_PROXY_COUNT        |                                    |
| rate_limit_storage_uri    | RATE_LIMIT_STORAGE_URI     |                                    |
| quota_enabled             | QUOTA_ENABLED              |                                    |
| turnstile_secret_key      | TURNSTILE_SECRET_KEY       |                                    |
| turnstile_site_key        | TURNSTILE_SITE_KEY         |                                    |

**For docker-compose ONLY — additional service env vars** (not in config.py):
- `VITE_API_BASE_URL` for the `web` service build-arg (frontend Vite build)
- `API_BASE_URL` for the `web` service nginx runtime (config.js injection)
- `ENABLE_BEAT` for the `worker` service

### 10. Test file pattern
All test files in `backend/tests/` follow the same pattern:
- Import from `app.*` directly (no conftest.py — that file does not exist)
- Local `_make_user`, `_create_workspace`, `_add_member`, `_auth_headers` helpers
- `@pytest.fixture def db()` yields a `SessionLocal()`
- `@pytest.fixture(autouse=True) def reset_limiter_and_tasks()` patches task apply_async
- `_settings_override(**kwargs)` context manager for settings mutation
- `TestClient(app)` as module-level `client`

---

## Implementation Plan

### Section 0 — Backend fixes

- [ ] 1. Fix provider-precedence logic in `resolve_email_providers`, `resolve_sms_provider`,
      `has_email_provider`, and `has_sms_provider`.

      New rule (all four functions):
      1. If workspace has own active ProviderCredential rows (for email: providers `brevo`/`smtp`; for SMS: provider `twilio`) → use ONLY those.
      2. Else if `workspace is None or workspace.use_platform_providers is True` → use platform settings.
      3. Else → no provider (empty list / None / False).

      Concrete change to `resolve_email_providers`:
      ```python
      def resolve_email_providers(db, workspace):
          # Step 1: own active credentials?
          if workspace is not None:
              creds = db.execute(
                  select(ProviderCredential).where(
                      ProviderCredential.workspace_id == workspace.id,
                      ProviderCredential.provider.in_(["brevo", "smtp"]),
                      ProviderCredential.is_active == True,
                  )
              ).scalars().all()
              if creds:
                  # build provider list from own creds (existing code)
                  ...
                  return providers
          # Step 2: platform fallback
          if workspace is None or workspace.use_platform_providers:
              return get_platform_email_providers()
          # Step 3: nothing
          return []
      ```
      Apply the same pattern to `resolve_sms_provider`, `has_email_provider`, `has_sms_provider`.

      No callers change — the functions' signatures and return types remain identical.

      Files: `backend/app/services/providers.py`
      Verify: `cd backend && pytest tests/test_tier4e_backend.py -q` — tests 1–4 pass.

- [ ] 2. Fix the Twilio status_callback URL in `resolve_sms_provider`.

      In the current code, when falling back to the platform provider,
      `get_platform_sms_provider()` uses `f"{settings.public_base_url}/webhooks/twilio"`
      (no workspace token). When using own credentials, it correctly uses
      `f"{settings.public_base_url}/webhooks/twilio/{workspace.webhook_token}"`.
      After the precedence fix in item 1, the own-creds path already has the correct callback URL.
      No change needed to the callback logic itself — verify by reading the new code path.

      Files: `backend/app/services/providers.py` (same file as item 1 — already done)
      Verify: read the function to confirm the callback URL is present on the own-creds path.

- [ ] 3. Confirm `SuppressionCreate.reason` — **no change needed**.

      The schema already has `reason: Literal["opt_out", "bounce"] = "opt_out"`.
      Skip writing code; document in test file that 422 is expected for `complaint`/`manual`.

      Files: none (already correct in `backend/app/schemas/notification.py`)
      Verify: `pytest tests/test_tier4e_backend.py::test_suppression_reason_complaint_rejected -q`

- [ ] 4. Fix `SuppressionsPage.jsx` reason options.

      Change:
      ```js
      const REASON_OPTIONS = ['opt_out', 'bounce', 'complaint', 'manual'];
      ```
      to:
      ```js
      const REASON_OPTIONS = ['opt_out', 'bounce'];
      ```

      Files: `frontend/src/pages/settings/SuppressionsPage.jsx`
      Verify: `cd frontend && npm run build` — exits 0.

- [ ] 5. Write `backend/tests/test_tier4e_backend.py` with 8 tests.

      Follow the exact pattern from `test_tier4c1.py` and `test_tier4d_backend.py`:
      - Module-level `client = TestClient(app)` and `settings = get_settings()`
      - `@pytest.fixture(autouse=True) def reset_limiter_and_tasks()` patching apply_async
      - `@pytest.fixture def db()` yielding SessionLocal
      - `_settings_override`, `_make_user`, `_create_workspace`, `_add_member`, `_auth_headers` helpers
      - `@pytest.fixture(autouse=True) def ensure_encryption_key()` (needed for provider cred tests)

      Tests:
      - **test_1_own_email_creds_win_over_platform**: Create workspace with `use_platform_providers=True`, add active Brevo ProviderCredential. Call `resolve_email_providers(db, ws)` → result must come from own cred (assert brevo from_email matches the one in the credential, not platform settings).
      - **test_2_fallback_to_platform_when_no_own_creds**: Create workspace with `use_platform_providers=True`, no ProviderCredential rows. `resolve_email_providers(db, ws)` → returns platform providers (non-empty if BREVO_API_KEY is set in env, or patch settings to have a key).
      - **test_3_no_creds_no_platform_fallback**: Create workspace with `use_platform_providers=False`, no ProviderCredential rows. `resolve_email_providers(db, ws)` → returns `[]`.
      - **test_4_own_sms_creds_win_over_platform**: Create workspace with `use_platform_providers=True`, add active Twilio ProviderCredential. `resolve_sms_provider(db, ws)` → TwilioConfig from own cred (assert from_number matches credential).
      - **test_5_suppression_reason_opt_out_accepted**: POST `/suppressions` with `reason="opt_out"` → status 200.
      - **test_6_suppression_reason_bounce_accepted**: POST `/suppressions` with `reason="bounce"` → status 200.
      - **test_7_suppression_reason_complaint_rejected**: POST `/suppressions` with `reason="complaint"` → status 422.
      - **test_8_suppression_reason_manual_rejected**: POST `/suppressions` with `reason="manual"` → status 422.

      For tests 1 and 4: use `encrypt_json` (from `app.services.crypto`) to create
      `config_encrypted` on the ProviderCredential. Patch settings to have a known
      `encryption_key` via `ensure_encryption_key` fixture.
      For test 2: use `_settings_override` to inject a dummy `brevo_api_key` and `brevo_from_email`.

      Files: `backend/tests/test_tier4e_backend.py`
      Verify: `cd backend && pytest tests/test_tier4e_backend.py -v` — all 8 tests pass.

---

### Section 1 — Frontend runtime config

- [ ] 6. Create `frontend/public/config.js`.

      Content:
      ```js
      // Runtime config — override VITE_API_BASE_URL at deploy time without rebuilding.
      window.__APP_CONFIG__ = {};
      ```
      This file is served statically. In production it will be overwritten by the Docker
      entrypoint script (Section 2) with actual values.

      Files: `frontend/public/config.js` (create)
      Verify: `cd frontend && npm run build` — `dist/config.js` appears in the output directory.

- [ ] 7. Update `frontend/index.html` to load config.js before the app bundle.

      Insert `<script src="/config.js"></script>` immediately before
      `<script type="module" src="/src/main.jsx"></script>`.

      Files: `frontend/index.html`
      Verify: `npm run build` and confirm `/config.js` reference present in `dist/index.html`.

- [ ] 8. Add `absoluteApiBase()` helper to `frontend/src/lib/api.js` and update all usages.

      a. Replace the module-level `BASE_URL` constant with a lazy function:
      ```js
      export function absoluteApiBase() {
        return (
          (window.__APP_CONFIG__ && window.__APP_CONFIG__.API_BASE_URL) ||
          import.meta.env.VITE_API_BASE_URL ||
          'http://localhost:8000'
        ).replace(/\/$/, '');
      }
      // Keep BASE_URL as a lazy alias so existing internal callers work
      function _base() { return absoluteApiBase(); }
      ```
      b. In `apiFetch`, replace `${BASE_URL}${path}` with `${_base()}${path}`.
      c. In the legacy `request` function, same replacement.
      d. Export `absoluteApiBase` so page components can import it.

      Files: `frontend/src/lib/api.js`
      Verify: `npm run build` exits 0.

- [ ] 9. Update `OverviewPage.jsx` and `ApiKeysPage.jsx` to use `absoluteApiBase()`.

      Both files currently compute the API base inline:
      - `OverviewPage.jsx`: `const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(...)` → replace with `import { absoluteApiBase } from '../lib/api'; const apiBase = absoluteApiBase();`
      - `ApiKeysPage.jsx`: `const API_BASE = (import.meta.env.VITE_API_BASE_URL || ...).replace(...)` → replace with `import { absoluteApiBase } from '../../lib/api'; const API_BASE = absoluteApiBase();`
        Also update `curlExample` and `templateExample` which use `API_BASE` — they are already module-level `const`s, so call `absoluteApiBase()` inside the component render or make them functions.

      Files:
      - `frontend/src/pages/OverviewPage.jsx`
      - `frontend/src/pages/settings/ApiKeysPage.jsx`
      Verify: `npm run build` exits 0.

- [ ] 10. Update `frontend/.env.example` to contain only one non-trivial entry.

      Keep exactly:
      ```
      VITE_API_BASE_URL=http://localhost:8000
      ```

      Files: `frontend/.env.example` (create or overwrite if it exists)
      Verify: file contains exactly one env var line.

---

### Section 2 — Docker files

- [ ] 11. Create `backend/Dockerfile`.

      Multi-stage or single-stage with python:3.11-slim. Key requirements:
      - Non-root user `app` (uid 1000)
      - `WORKDIR /app`
      - Copy `requirements.txt`, run `pip install --no-cache-dir`
      - Copy app source
      - **No default CMD** — CMD is set per-service in docker-compose.yml
      - No exposed port (API and worker use different start commands)

      ```dockerfile
      FROM python:3.11-slim
      RUN useradd -m -u 1000 app
      WORKDIR /app
      COPY requirements.txt .
      RUN pip install --no-cache-dir -r requirements.txt
      COPY . .
      USER app
      ```

      Files: `backend/Dockerfile`
      Verify: `docker build backend/` exits 0 (or `docker compose build api` if compose is ready).

- [ ] 12. Create `backend/.dockerignore`.

      Exclude:
      ```
      __pycache__
      *.pyc
      *.pyo
      .env
      .env.*
      venv/
      .venv/
      tests/
      alembic/versions/*.pyc
      *.sql
      ```

      Files: `backend/.dockerignore`
      Verify: docker build does not copy venv or .env files.

- [ ] 13. Create `frontend/nginx.conf`.

      Configuration:
      - Listen on port 80
      - `root /usr/share/nginx/html`
      - SPA fallback: `try_files $uri $uri/ /index.html`
      - `/api/` proxy: `proxy_pass http://api:8000/;` with appropriate headers
      - Gzip: `gzip on; gzip_types text/plain application/javascript application/json text/css`
      - Cache headers: `location ~* \.(js|css|png|svg|ico|woff2)$ { expires 1y; add_header Cache-Control "public, immutable"; }` but `location = /config.js { expires off; add_header Cache-Control "no-store"; }` (config.js must never be cached)
      - Security headers: `X-Frame-Options SAMEORIGIN; X-Content-Type-Options nosniff; Referrer-Policy strict-origin-when-cross-origin`

      Files: `frontend/nginx.conf`
      Verify: `docker compose build web` exits 0.

- [ ] 14. Create `frontend/Dockerfile`.

      Multi-stage:
      - Stage 1 `builder`: `FROM node:20-alpine AS builder`; copy `package*.json`, `npm ci`; copy source; `ARG VITE_API_BASE_URL`; `RUN npm run build`
      - Stage 2 `runner`: `FROM nginx:alpine`; copy nginx.conf; copy `--from=builder /app/dist /usr/share/nginx/html`; copy `frontend/docker-entrypoint.d/` to `/docker-entrypoint.d/`; expose 80

      Files: `frontend/Dockerfile`
      Verify: `docker compose build web` exits 0.

- [ ] 15. Create `frontend/docker-entrypoint.d/10-config.sh`.

      Writes `config.js` at container startup from environment variables:
      ```sh
      #!/bin/sh
      cat > /usr/share/nginx/html/config.js <<EOF
      window.__APP_CONFIG__ = {
        API_BASE_URL: "${API_BASE_URL:-}"
      };
      EOF
      ```
      Make it executable (chmod +x in Dockerfile or in the script via `RUN chmod`).

      Files: `frontend/docker-entrypoint.d/10-config.sh`
      Verify: script syntax is valid; `docker compose up web` writes config.js correctly.

- [ ] 16. Create `frontend/.dockerignore`.

      ```
      node_modules/
      dist/
      .env
      .env.*
      *.log
      ```

      Files: `frontend/.dockerignore`
      Verify: build excludes node_modules.

- [ ] 17. Create `docker-compose.yml` at the repo root.

      Services:
      - **db**: `image: postgres:16`; env `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`; volume `pgdata`; healthcheck `pg_isready`
      - **redis**: `image: redis:7-alpine`; healthcheck `redis-cli ping`
      - **migrate**: `build: ./backend`; `command: alembic upgrade head`; `depends_on: {db: {condition: service_healthy}}`; env includes `DATABASE_URL`; `restart: on-failure`
      - **api**: `build: ./backend`; `command: uvicorn app.main:app --host 0.0.0.0 --port 8000`; `depends_on: {migrate: {condition: service_completed_successfully}, redis: {...}}`; env includes ALL backend env vars from the table in finding 9; ports `8000:8000`
      - **worker**: `build: ./backend`; `command: python worker_wrapper.py`; same depends_on as api; same env; env also has `ENABLE_BEAT=false`
      - **web**: `build: {context: ./frontend, args: {VITE_API_BASE_URL: /api}}`; `depends_on: [api]`; env `API_BASE_URL=/api`; ports `80:80`

      IMPORTANT: celery_app.py reads `REDIS_URL` for both broker and backend. Do NOT add
      `CELERY_BROKER_URL` or `CELERY_RESULT_BACKEND` as separate entries — they are not read.
      
      Use `env_file: .env` on api and worker services so `.env` at repo root is loaded.

      Volumes: `pgdata:` named volume.

      Files: `docker-compose.yml`
      Verify: `docker compose config` exits 0 (validates the YAML).

- [ ] 18. Create root `.env.example` with ALL settings from config.py.

      Must include every field from the findings table in section 9. Use the values from
      `backend/.env.example` as the template. Add a preamble comment block. The file should
      be a complete working template for a fresh self-hosted deployment.

      Key differences from `backend/.env.example`:
      - Add `POSTGRES_DB=notification_db`, `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=changeme` (docker-compose db service vars)
      - Add `VITE_API_BASE_URL=http://localhost:8000` (frontend Vite build)
      - Add `API_BASE_URL=http://localhost:8000` (nginx runtime injection)
      - Add `ENABLE_BEAT=false`
      - No duplicate sections (the backend `.env.example` has some duplicate keys — omit them)

      Files: `.env.example`
      Verify: file exists and contains `DATABASE_URL`, `REDIS_URL`, `API_KEY`, `JWT_SECRET`.

- [ ] 19. Create `scripts/generate_env.py` (stdlib only).

      Script that reads `.env.example`, finds lines containing `SECRET`, `KEY`, `TOKEN`,
      `PASSWORD` (case-insensitive) with empty or placeholder values, generates cryptographically
      random replacements, and writes a `.env` file.

      ```python
      #!/usr/bin/env python3
      """Generate .env from .env.example with random secrets filled in."""
      import secrets
      import sys
      from pathlib import Path
      ...
      ```

      Logic:
      - Read `.env.example`
      - For each `KEY=placeholder_or_empty` line, if key contains `SECRET|KEY|TOKEN|PASSWORD|SALT`,
        replace value with `secrets.token_urlsafe(32)`
      - Exception: `ENCRYPTION_KEY` → generate a Fernet key (base64url, 44 chars, padding `=`):
        `base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()`
      - Write to `.env`, skipping if `.env` already exists (print warning, no overwrite)

      Files: `scripts/generate_env.py`
      Verify: `python scripts/generate_env.py` creates `.env` with non-empty values for secret fields.

- [ ] 20. Add `.env`, `dist/`, and Docker artifact entries to root `.gitignore`.

      Append to `.gitignore`:
      ```
      .env
      docker-compose.override.yml
      frontend/dist/
      backend/__pycache__/
      backend/.pytest_cache/
      *.log
      ```

      Files: `.gitignore`
      Verify: `git status` does not show `.env` as tracked after the file is created.

---

### Section 3 — Landing page and docs

- [ ] 21. Create `frontend/src/pages/LandingPage.jsx`.

      A public marketing page for logged-out visitors. Sections:
      - **Hero**: headline "Open-source notification infrastructure", subheadline, two CTA buttons (`/login` and `#features`)
      - **Features**: 3 feature cards (Multi-channel, Templates, API-first)
      - **How it works**: 3-step visual (Configure provider → Create API key → Send notification)
      - **Live API example**: curl snippet using `absoluteApiBase()` with syntax highlighting (use `<pre>` with a copy button)
      - **Footer**: GitHub link, MIT license badge, `/login` link

      Component must be fully self-contained (no auth required), use Tailwind classes consistent
      with the existing design system (gray-900 background, blue-600 accents, same font sizes).
      Import `absoluteApiBase` from `../lib/api`.

      Files: `frontend/src/pages/LandingPage.jsx` (create)
      Verify: `npm run build` exits 0.

- [ ] 22. Create `frontend/src/pages/DocsPage.jsx`.

      Full API reference page. Structure:
      - Sticky left sidebar with anchor links to sections
      - Sections: Authentication, Send Email, Send SMS, Send Webhook, Bulk, Templates, Suppressions
      - Each section shows the endpoint method+path, a description, request schema, example curl using `absoluteApiBase()`, example response
      - Copy buttons on all code blocks
      - Mobile-responsive: sidebar collapses on small screens

      Import `absoluteApiBase` from `../lib/api`.

      Files: `frontend/src/pages/DocsPage.jsx` (create)
      Verify: `npm run build` exits 0.

- [ ] 23. Update `frontend/src/App.jsx` to add LandingPage and DocsPage routes and fix `/` auth logic.

      Changes:
      a. Import `LandingPage` and `DocsPage`.
      b. The `/` route: currently always requires auth and renders OverviewPage. Change to check
         auth: if authenticated → OverviewPage, else → LandingPage. Use the existing `useAuth` hook
         or a conditional inside a wrapper component.
         
         Simplest approach — create a small `HomeRoute` component inline in App.jsx:
         ```jsx
         function HomeRoute() {
           const { user } = useAuth();
           return user ? (
             <RequireAuth><Layout><OverviewPage /></Layout></RequireAuth>
           ) : (
             <LandingPage />
           );
         }
         ```
         Then `<Route path="/" element={<HomeRoute />} />`.
      c. Add `/docs` route (public, no auth required):
         ```jsx
         <Route path="/docs" element={<DocsPage />} />
         ```

      Files: `frontend/src/App.jsx`
      Verify: `npm run build` exits 0.

- [ ] 24. Update `frontend/src/components/Layout.jsx` to add a Docs nav link.

      Add to the `NAV` array:
      ```js
      { to: '/docs', label: 'Docs', exact: false },
      ```
      Position: after `Overview`, before `Notifications` (or at the end before Settings).
      Keep it non-restricted (no `adminOnly` or `superadminOnly`).

      Files: `frontend/src/components/Layout.jsx`
      Verify: `npm run build` exits 0.

---

### Section 4 — OSS files

- [ ] 25. Create `LICENSE` (MIT, current year, author "Notification Service Contributors").

      Files: `LICENSE`
      Verify: file exists and contains "MIT License".

- [ ] 26. Create `README.md` (full rewrite).

      Sections:
      - Badge row: CI badge, MIT license, Docker
      - One-line description
      - Mermaid architecture diagram (client → API → Celery Worker → Provider; also DB and Redis)
      - Quickstart (3 commands: clone, `python scripts/generate_env.py`, `docker compose up`)
      - Features list
      - Configuration reference table (all env vars from finding 9, with Description and Default columns)
      - REST API quick-reference table (method, path, description)
      - Development setup (manual Python + Node steps)
      - Contributing link
      - License

      Files: `README.md`
      Verify: file exists, contains `## Quickstart` and a Mermaid code block.

- [ ] 27. Create `docs/self-hosting.md`.

      Content:
      - Prerequisites (Docker 24+, Docker Compose v2)
      - Step-by-step: clone → generate_env.py → review `.env` → `docker compose up -d`
      - Service descriptions (what each docker-compose service does)
      - How to run migrations manually
      - How to enable the scheduler (ENABLE_BEAT=true)
      - Backup / restore for the postgres volume
      - Upgrading

      Files: `docs/self-hosting.md`
      Verify: file exists and contains a `## Prerequisites` section.

- [ ] 28. Create `docs/deployment.md`.

      Content:
      - Environment variable reference (same table as README, more verbose)
      - Scaling: running multiple API workers, multiple Celery workers
      - Using an external managed Postgres and Redis
      - Reverse proxy setup (nginx / Cloudflare)
      - TRUSTED_PROXY_COUNT and rate limit storage
      - TLS / HTTPS considerations

      Files: `docs/deployment.md`
      Verify: file exists.

- [ ] 29. Create `CONTRIBUTING.md`.

      Content:
      - How to fork and run locally (backend: `pip install -r requirements.txt`, `alembic upgrade head`, `uvicorn app.main:app --reload`; frontend: `npm ci && npm run dev`)
      - How to run tests: `cd backend && pytest -q`
      - How to run linting: `npm run lint`
      - Commit style (Conventional Commits)
      - PR process
      - Code of conduct reference

      Files: `CONTRIBUTING.md`
      Verify: file exists and contains `## Running Tests`.

- [ ] 30. Create `SECURITY.md`.

      Content:
      - Supported versions
      - How to report a security vulnerability (private email or GitHub security advisory)
      - What we consider a security issue
      - Response timeline
      - Hall of fame / credits section

      Files: `SECURITY.md`
      Verify: file exists and contains `## Reporting`.

- [ ] 31. Create `.github/pull_request_template.md`.

      Template sections: Description, Type of change (checkbox list), How Has This Been Tested?,
      Checklist (lint, tests pass, docs updated, no secrets committed).

      Files: `.github/pull_request_template.md`
      Verify: file exists.

- [ ] 32. Create `.github/ISSUE_TEMPLATE/bug_report.md` and `feature_request.md`.

      Standard GitHub issue templates with YAML front-matter (`name`, `about`, `labels`).

      Files:
      - `.github/ISSUE_TEMPLATE/bug_report.md`
      - `.github/ISSUE_TEMPLATE/feature_request.md`
      Verify: both files exist and contain valid front-matter.

---

### Section 5 — CI additions

- [ ] 33. Add `docker` job to `.github/workflows/ci.yml`.

      Append a new job after the existing `frontend` job:
      ```yaml
      docker:
        name: Docker Build Check
        runs-on: ubuntu-latest
        steps:
          - name: Checkout repository
            uses: actions/checkout@v4

          - name: Validate docker-compose config
            run: docker compose config --quiet

          - name: Build backend image
            run: docker compose build api

          - name: Build frontend image
            run: docker compose build web
      ```

      This job does NOT start the services (no `up`), it only validates the YAML and
      builds images to catch Dockerfile errors in CI.

      Files: `.github/workflows/ci.yml`
      Verify: `cat .github/workflows/ci.yml` shows the new `docker` job; YAML is valid
      (`docker compose config` passes locally).

---

## Complete ordered file list

### Files to create (new)
1. `backend/tests/test_tier4e_backend.py`
2. `frontend/public/config.js`
3. `frontend/.env.example`
4. `backend/Dockerfile`
5. `backend/.dockerignore`
6. `frontend/nginx.conf`
7. `frontend/Dockerfile`
8. `frontend/docker-entrypoint.d/10-config.sh`
9. `frontend/.dockerignore`
10. `docker-compose.yml`
11. `.env.example`
12. `scripts/generate_env.py`
13. `frontend/src/pages/LandingPage.jsx`
14. `frontend/src/pages/DocsPage.jsx`
15. `LICENSE`
16. `README.md`
17. `docs/self-hosting.md`
18. `docs/deployment.md`
19. `CONTRIBUTING.md`
20. `SECURITY.md`
21. `.github/pull_request_template.md`
22. `.github/ISSUE_TEMPLATE/bug_report.md`
23. `.github/ISSUE_TEMPLATE/feature_request.md`

### Files to modify (existing)
1. `backend/app/services/providers.py` — provider precedence fix
2. `frontend/src/pages/settings/SuppressionsPage.jsx` — remove complaint/manual options
3. `frontend/index.html` — add config.js script tag
4. `frontend/src/lib/api.js` — add absoluteApiBase(), update BASE_URL usage
5. `frontend/src/pages/OverviewPage.jsx` — use absoluteApiBase()
6. `frontend/src/pages/settings/ApiKeysPage.jsx` — use absoluteApiBase()
7. `frontend/src/App.jsx` — HomeRoute, LandingPage, DocsPage routes
8. `frontend/src/components/Layout.jsx` — add Docs nav link
9. `.github/workflows/ci.yml` — add docker job
10. `.gitignore` — add .env and dist entries

---

## Verification commands (real project commands)

```bash
# Backend tests (requires running postgres on localhost:5432)
cd backend && pytest tests/test_tier4e_backend.py -v

# Full backend suite
cd backend && pytest -q

# Frontend build
cd frontend && npm run build

# Docker compose validation (no containers started)
docker compose config --quiet
docker compose build api
docker compose build web
```
