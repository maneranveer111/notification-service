# Frontend Auth Pages — Status

**Completed** — commit `75f64a7` on branch `tier-1`

## Pages created / updated

| File | Status | Notes |
|------|--------|-------|
| `src/pages/SignupPage.jsx` | ✅ NEW | config-gated (closed/invite_only/needs_setup), captcha, check-inbox + resend with 60 s cooldown |
| `src/pages/LoginPage.jsx` | ✅ REWRITE | getPublicConfig, describeError, 403+email_not_verified → resend mode, signup link gated by signup_mode |
| `src/pages/VerifyEmailPage.jsx` | ✅ NEW | verbatim from spec; uses calledRef to prevent double-POST |
| `src/pages/ForgotPasswordPage.jsx` | ✅ NEW | always shows "we sent a link" after submit |
| `src/pages/ResetPasswordPage.jsx` | ✅ NEW | client-side match+length validation, success/failed states |
| `src/pages/AcceptInvitePage.jsx` | ✅ NEW | all 4 branches (a/b/c/d) per backend InvitationInfoResponse schema |
| `src/App.jsx` | ✅ UPDATED | added routes: /signup, /verify-email, /forgot-password, /reset-password, /accept-invite |

## Verified
- `npm run build` passes with 0 errors (chunk-size warning is pre-existing, unrelated)
- No backend files touched
- api.js, auth.jsx, errors.js untouched
