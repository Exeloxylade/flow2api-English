# Desktop browser login contract

The automatic desktop flow consists of a local browser helper and an authenticated server handoff. Bang Story orchestrates installation, private browser profiles, cancellation, and account UI. Standalone servers still support manual account import; this feature does not open a browser on a remote server.

## Browser helper (Windows)

`src/services/browser_login.py` runs in the installed Python environment with Playwright available. Its caller provides:

- `BANG_LOGIN_PROFILE`: an app-owned, per-account browser profile directory, created by the caller.
- `BROWSER_EXECUTABLE_PATH`: an installed Chrome or managed Chromium executable.
- `BANG_LOGIN_EMAIL`: the expected email for reconnect, or empty for adding an account.

The helper opens a normal visible browser with that profile and an ephemeral CDP port on loopback. It waits up to ten minutes for a signed-in `flow.google.com` page, reads the Flow bootstrap identity, and exports only unpartitioned Google-domain cookies when both Flow session and Google account cookies are present. It requests no Google password; verification is completed directly with Google.

On success it writes exactly one JSON object with `email` and `cookies` to stdout. **That output contains credentials: consume it over a private subprocess pipe. Never display it, log it, or redirect it to a file.** stderr is not used to expose underlying browser errors. The helper closes its own browser before returning.

Exit codes: `0` success, `2` browser closed, `3` wrong reconnect identity, `4` login timeout, `5` browser/setup failure. The caller must bound stdout, enforce its own timeout, and terminate the helper/browser process tree when cancelled. Bang Story uses isolated UUID directories and records profile mappings only after server registration succeeds.

## Registration endpoint

`POST /api/tokens/browser-session` requires a current admin session (`Authorization: Bearer <admin-session>` or the existing admin session cookie). A generation API key is insufficient. Send credentials only to a server you control; Bang Story uses its loopback server.

Request fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `login_account` | email string | Identity captured from the Flow page |
| `google_cookies` | JSON string | Full scoped Google/Flow cookie array |
| `expected_account_id` | positive integer or null | Existing account that must match when reconnecting |

Unknown fields, malformed emails, and invalid IDs are rejected. The server fetches the current Flow frontend with the cookie jar and checks its observed email against `login_account`. Cookies alone or a claimed email do not bypass identity validation. A reconnect target that has been removed or belongs to another account cannot create a replacement account.

Registrations through this endpoint are serialized. An existing email updates the stored session while preserving its project, model permissions, proxy, and concurrency settings. Disabled accounts are enabled only after the new session validates. New emails use the existing token manager defaults. Automatic session refresh is enabled for both cases.

A successful response contains only `success`, `action` (`added`/`updated`), and `account` (`id`, `email`, `enabled`). It never contains cookies, session tokens, or access tokens. Invalid sessions return a safe 400 error; unexpected upstream failures return a fixed 502 message. Credentials remain stored by the existing server database and managed browser; the database is not newly encrypted by this feature.

## Regression checks

```powershell
python -X utf8 -m unittest discover -s tests -p test_browser_accounts.py
python -X utf8 -m unittest discover -s tests -p test_browser_login.py
python -X utf8 -m unittest discover -s tests
python -m compileall -q src
```

The new tests exercise authentication, server-observed identity checks, duplicate and parallel logins, reconnect validation, response redaction, profile/browser shutdown, and cookie filtering using test doubles. They do not establish live Google login or generation success.
