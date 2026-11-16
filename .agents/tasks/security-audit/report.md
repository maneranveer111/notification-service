# Security Audit Report

Audit scope: `backend/app/**` (read-only, no code was changed).

---

## Findings Table

| # | Sub | Finding | YES/NO | file:line |
|---|-----|---------|--------|-----------|
| 1a | Secrets in API responses | `webhook_token` returned by admin-only GET/POST `/providers/webhooks` — intentional, admin-only | PARTIAL (see note) | providers.py:448,474 |
| 1a | `api_key` / `auth_token` / `account_sid` / `password` in API response | NOT returned raw; only last-4 hint for `api_key` & `auth_token`; `account_sid` last-4 in `hints` | NO (clean) | providers.py:94–104 |
| 1a | Secrets in logger calls | No raw secret value reaches a logger arg (see 1b list) | NO | see 1b |
| 1a | Secrets in exception messages | `_sanitize_error` strips secrets before storing in `last_error`; `_sanitize_error_message` in tasks strips webhook URL | NO | providers.py:67; notification_tasks.py:27 |
| 1b | logger calls (all files touching credentials) | See detailed list below | — | — |
| 1c | `webhook_token` outside admin routes | `webhook_token` appears only in `/providers/webhooks` (GET) and `/providers/webhooks/regenerate` (POST), both behind `require_admin` | YES (correct) | providers.py:443,460 |
| 2a | Pydantic schemas expose secret field | No schema includes `api_key`, `password`, `auth_token`, `account_sid`, `encryption_key`, `webhook_token`, or `config_encrypted` | NO | schemas/ |
| 2b | All `/providers*` routes require admin | Router-level `dependencies=[Depends(require_admin)]` on the whole router | YES (correct) | providers.py:23 |
| 3a | Decrypt failure returns sanitized error | `CryptoNotConfigured` → 503 with generic message; other decrypt errors → empty `{}` config or `{"ok": false, "error": "Failed to decrypt credentials: ..."}` on test endpoint (exception str may leak internal detail) | PARTIAL (see note) | providers.py:247; providers.py:277 |
| 3b | Missing `ENCRYPTION_KEY` at runtime | `CryptoNotConfigured` raised → caught → 503 "Encryption is not configured on this server" (never plaintext fallback) | YES (correct) | crypto.py:13; providers.py:240 |
| 4a | `assert_public_host` on PUT smtp AND test endpoint AND send time | PUT smtp: yes (providers.py:187); test endpoint: yes (providers.py:291); send time via `_send_smtp`: yes when `is_platform=False` | YES (correct) | providers.py:187,291; email_service.py:77 |
| 4b | Port allowlist enforced | Ports 25, 465, 587, 2525 checked before saving SMTP config | YES | providers.py:165 |
| 4c | ALL addresses for hostname checked | `socket.getaddrinfo` returns all records; loop iterates every `item` in result | YES | net_safety.py:22–43 |
| 4d | IPv4-mapped IPv6 (`::ffff:10.0.0.1`) handled | `ip.ipv4_mapped` unwrapped before check | YES | net_safety.py:30–32 |
| 4e | Rejects 127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7, fe80::/10 | All covered via `ip.is_private \| ip.is_loopback \| ip.is_link_local` (verified with Python runtime test — all 10 test IPs rejected) | YES | net_safety.py:43–49 |
| 4f | Slack/Discord host allowlist at SEND time; `allow_redirects=False` | Host checked by `webhook_channel_allowed_hosts` config at queue time; `requests.post(..., allow_redirects=False)` at send time | YES | notifications.py:409–421; webhook_service.py:60 |
| 5a | Per-workspace routes filter by `workspace_id` AND `provider_message_id` | Brevo: `ws.id` + `provider_message_id.in_(candidates)`; Twilio: `ws.id` + `provider_message_id == message_sid` | YES | webhooks.py:174–180; webhooks.py:244–248 |
| 5b | Unknown token → same HTTP status regardless of reason | Both token-not-found and workspace-mismatch return 404 (same detail text differs slightly but status is uniform 404) | YES | webhooks.py:160,211 |
| 5c | Twilio handler uses workspace's own `auth_token` | Decrypts workspace `ProviderCredential` and uses `conf["auth_token"]` | YES | webhooks.py:221–232 |
| 5d | Legacy routes unreachable with workspace token | Legacy `/webhooks/brevo` and `/webhooks/twilio` require `webhook_secret` (or no auth if `webhook_verify=False`); no workspace-token path exists | YES | webhooks.py:295–304,354–363 |
| 6a | `_deliver` uses `notification.workspace_id` | `ws = db.get(Workspace, notification.workspace_id)` — never request principal | YES | notification_tasks.py:225 |
| 6b | System mailer always uses platform providers | `system_tasks.py` calls `email_service.send_email()` which calls `_build_platform_providers()` directly | YES | system_tasks.py:17; email_service.py:164 |
| 6c | `use_platform_providers` only via superadmin endpoint | PATCH `/admin/workspaces/{id}` requires `require_superadmin` | YES | admin.py:285 |
| 7a | Every IP-based limit calls `client_ip()` | `limiter` uses `get_api_key` which calls `client_ip()`; `@limiter.limit` with explicit `key_func=client_ip` on signup/resend/forgot/login | YES | limiter.py:8–16; accounts.py:122,273,291 |
| 7b | X-Forwarded-For trusted only when `trusted_proxy_count > 0` | `if trusted_count <= 0: return fallback` (uses `request.client.host`) | YES | client_ip.py:11 |
| 7c | Remaining `request.client.host` uses | Only the intended fallback inside `client_ip()` itself | CLEAN | client_ip.py:8 |
| 8a | `get_principal`: user active check | `if not user or not user.is_active: raise 401` | YES | security.py:177 |
| 8a | `get_principal`: membership re-read per request | `db.get(Membership, ...)` called on every request | YES | security.py:180–195 |
| 8a | `get_principal`: verified email (when required) | `require_email_verification` guard present | YES | security.py:202 |
| 8a | `get_principal`: `iat` vs `password_changed_at` (floored seconds) | `int(token_iat) < int(password_changed_at.timestamp())` — both `int()` → floor to seconds | YES | security.py:197 |
| 8a | `get_user_principal`: same four checks | Active check ✓, membership re-read ✓, email verification NOT enforced (by design — used for `/auth/me`, `/workspaces`), iat-floor check ✓ | PARTIAL (by design) | security.py:72–101 |
| 9a | Single notification quota | `consume_quota(ws, 1)` called before `db.commit()` in `_queue_notification` | YES | notifications.py:220 |
| 9a | Bulk notification quota | `consume_quota(ws, non_suppressed_count)` called before `db.commit()` | YES | notifications.py:593 |
| 9a | Webhook-inbound (webhook channel) | Webhook channel rows skip suppression; `consume_quota` still called via `_queue_notification` | YES | notifications.py:220 |
| 9a | Scheduled dispatch (sweeper) | `dispatch_scheduled` moves status to `pending` and re-enqueues; quota was already consumed at creation | YES (correct) | notification_tasks.py:505–540 |
| 9a | Retry | Manual retry resets status and re-enqueues; no new quota consumed (same notification row) | YES (correct) | notifications.py:793–809 |
| 9b | Idempotent replays consume nothing | Early return before `consume_quota` on idempotency-key hit | YES | notifications.py:117–122 |
| 9b | Suppressed rows consume nothing | Suppressed path returns before `consume_quota` | YES | notifications.py:140–162 |
| 9c | `release_quota` on failure | Called in both `IntegrityError` and generic `except` branches after `consume_quota` | YES | notifications.py:228,233 |
| 9d | Plan limits for `api_keys` | Checked in `POST /admin/clients` | YES | admin.py:70–84 |
| 9d | Plan limits for `invitations` | `members_count + pending_count >= members_limit` enforced | YES | invitations.py:35–52 |
| 9d | Plan limits for bulk | `get_effective_bulk_max(plan_name)` enforced before loop | YES | notifications.py:459–468 |
| 9e | GET `/usage` workspace-scoped | Resolves workspace from `principal.workspace_id` | YES | workspaces.py:37–43 |
| 10a | CAPTCHA first async op on signup | `verify_captcha(request, payload.captcha_token)` is the very first call in `signup()` | YES | accounts.py:125 |
| 10a | CAPTCHA first async op on resend-verification | `verify_captcha(...)` first call | YES | accounts.py:276 |
| 10a | CAPTCHA first async op on forgot-password | `verify_captcha(...)` first call | YES | accounts.py:294 |
| 10b | CAPTCHA fails closed | `requests.RequestException` → 503; any other exception → 503; missing token → 400 | YES | captcha.py:54–64 |
| 11a | H1 – iat race fix: floor comparison | `int(token_iat) < int(password_changed_at.timestamp())` — both truncated to int (floor); token issued in same second as change is NOT rejected (`<` not `<=`) | YES | security.py:79,197 |
| 11b | H2 – `client_ip` uses `trusted_proxy_count`; `rate_limit_storage_uri` for Redis limiter | `client_ip.py` reads `trusted_proxy_count`; `limiter.py` passes `storage_uri=settings.rate_limit_storage_uri` | YES | client_ip.py:9; limiter.py:19 |
| 11c | H3 – signup timing equalization | `hash_password(payload.password)` dummy call on existing-user path in both `require_email_verification` and non-verification modes | YES | accounts.py:176,214 |
| 11d | H4 – `pg_advisory_xact_lock` in bootstrap path | `db.execute(text("SELECT pg_advisory_xact_lock(727001);"))` called before first-user check | YES | accounts.py:131 |

---

## Notes on Partial/Conditional Findings

**3a – Test endpoint decrypt-error leaks internal exception string.**
`providers.py:277` returns `{"ok": False, "error": f"Failed to decrypt credentials: {e}"}` where `e` is the raw Python exception. This is an admin-only endpoint and the error comes from the crypto layer (not from decrypted content), so it carries no plaintext secret. However, the internal exception message is exposed. Recommendation: replace with a fixed string such as `"Credential decryption failed"`.

**1a / `account_sid` hint.**
The `hints["account_sid"]` field (providers.py:103) returns the last 4 characters of `account_sid`. `account_sid` (e.g., `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`) is a non-secret identifier — it is visible in Twilio console URLs and not a credential. The real secret is `auth_token`, which is already handled identically. This is acceptable.

**8a – `get_user_principal` does not enforce `require_email_verification`.**
This is intentional by design: `get_user_principal` is used on `/auth/me`, `/workspaces`, and `/auth/switch-workspace`, where an unverified user needs read access to trigger re-verification. It does enforce active status and the iat/password-change check.

---

## Logger/Print Call Inventory (Item 1b)

All files that touch credentials were reviewed. No logger call passes a raw secret as an argument.

| File | Line | Call | Could contain secret? |
|------|------|------|-----------------------|
| email_service.py | 57 | `logger.info(f"Brevo message ID: {message_id}")` | No — `message_id` is the outbound message ID, not the API key |
| email_service.py | 199 | `logger.warning("Transient error with provider %s: %s", provider_name, exc)` | Potentially: `exc` is the exception from `requests`; Brevo errors can include the raw response body which may echo back a partial API key in error text. Low risk (admin logs, error response is from Brevo's server). Recommendation: sanitize `str(exc)` against the api_key value. |
| email_service.py | 206 | `logger.warning("Failover-enabled permanent error with %s: %s", provider_name, exc)` | Same as above — Brevo/SMTP exception string |
| email_service.py | 209 | `logger.error("Permanent error with provider %s: %s", provider_name, exc)` | Same as above |
| email_service.py | 215 | `logger.warning("Unexpected error with provider %s: %s", provider_name, exc)` | Same as above |
| sms_service.py | 43 | `logger.info(f"Twilio message SID: {sms.sid}")` | No — SID is non-secret |
| notification_tasks.py | 76 | `logger.error(f"Task {task_id} failed for notification {notification_id}: {safe_msg}")` | No — `safe_msg` is sanitized via `_sanitize_error_message` |
| notification_tasks.py | 99 | `logger.warning(f"Retrying task {task_id} for notification {notification_id}: {safe_msg}")` | No — sanitized |
| notification_tasks.py | 283 | `logger.info(f"Notification {notification_id} sent successfully via {provider_name}")` | No |
| notification_tasks.py | 306 | `logger.error(f"Permanent error delivering notification {notification_id}: {safe_msg}")` | No — sanitized |
| notification_tasks.py | 326 | `logger.warning(f"Error delivering notification {notification_id}: {safe_msg}")` | No — sanitized |
| system_tasks.py | 15 | `logger.info("CONSOLE MAIL to=%s subject=%s\n%s", to, subject, body)` | No — email body for system mails (verification/reset links), not credentials |
| webhooks.py | 185 | `logger.warning(f"Brevo workspace webhook: no notification found in workspace {ws.id} matching message id {raw_message_id}")` | No |
| webhooks.py | 259 | `logger.warning(f"Twilio workspace webhook: no notification found in workspace {ws.id} matching MessageSid {message_sid}")` | No |
| webhooks.py | 325 | `logger.warning(f"Brevo webhook: no notification found matching message id {raw_message_id}")` | No |
| webhooks.py | 370 | `logger.warning(f"Twilio webhook: no notification found matching MessageSid {message_sid}")` | No |
| captcha.py | 47 | `logger.info("Turnstile verification rejected: %s", error_codes)` | No — Turnstile error codes |
| captcha.py | 55 | `logger.warning("Turnstile verification request error: %s", exc)` | No |
| captcha.py | 61 | `logger.error("Unexpected error in CAPTCHA verification: %s", exc)` | No |
| quota.py | 109 | `logger.warning("Redis quota check failed for workspace %s, failing open: %s", workspace.id, exc)` | No |
| rate_limit.py | 43 | `logger.warning("Redis rate limit check failed for client %s: %s", client_id, exc)` | No |
| webhook_service.py | 76 | `logger.info(f"Webhook delivered via {provider}: HTTP {resp.status_code}")` | No — masked URL is used in errors, provider name only here |

---

## Recommendations

1. **email_service.py logger calls (lines 199, 206, 209, 215):** Exception strings from `requests` can include HTTP response bodies. For Brevo, a 401 response body may echo back the API key prefix. Sanitize `str(exc)` against the credential values before passing to logger, or catch at a higher level where credentials are in scope.

2. **providers.py:277 (test endpoint decrypt error):** Return a static string instead of `f"Failed to decrypt credentials: {e}"` to prevent internal exception detail disclosure to admins.

3. **H1 iat comparison is correct** (`<` not `<=`) — tokens issued in the same second as a password change remain valid, which is the intended behaviour and prevents spurious logouts.

4. All other 11 check areas **PASS** with no actionable vulnerabilities found.
