# Desktop browser login contract

## Current default: explicit browser-extension pairing

The dashboard and Bang Story use `ExtensionLogin`, not the automated helper below. The user signs in normally in their own Chrome/Edge profile. Connector 1.1.0 includes a Manifest V3 popup and a background service worker that keeps an authenticated loopback WebSocket. It stores a local pairing capability and account/tab mapping, without storing cookies or passwords or using an external extension service.

- Admin-authenticated, local same-origin `POST /api/browser-login/start` creates a one-use capability valid for 10 minutes. The authenticated status response includes `pairing_code` (`port:64-hex-token`) and a separate job ID. Pairing codes may be displayed/copied by the UI, but are never logged, placed in URLs, or persisted.
- The extension operates only after an explicit click on a signed-in `https://flow.google.com` studio tab. It reads that tab's cookie store and Flow bootstrap email, then sends scoped unpartitioned Google cookies directly to `http://127.0.0.1:<paired-port>/api/browser-login/extension` using the capability as a Bearer token. Redirects are forbidden; no desktop IPC carries cookies.
- The receiving endpoint requires a loopback peer and Host, an extension Origin if present, and `X-Flow-Connector: 1`. The high-entropy capability is required even when Chromium omits Origin for an extension with host permission. Web Origins are rejected. The endpoint grants no account-list or admin access.
- The server consumes the capability before awaiting verification, independently verifies Flow identity using the existing registration function, binds reconnect to the target captured at pairing creation, and returns account metadata only. Verification is bounded to 120 seconds. Failed verification requires a new pairing code; input and upstream errors are sanitized.
- Connector 1.1.0 explicitly requests live-browser pairing. Its account identity is read inside the user's Flow tab. Copied-cookie validation on the server is not treated as proof the RPC session works. After pairing, a new random capability is returned only to that extension request; its SHA-256 hash is saved per account. The capability never enters the dashboard's polled login state or account export.
- `/api/browser-session/ws` requires a loopback Host/peer, extension Origin and the matching per-account capability in the first message (never in the URL). Each RPC/CAPTCHA job is sent only to its authenticated account socket. The fixed extension script verifies the tab identity, accepts only allowlisted Flow RPCs and local Flow paths, and uses the real page's session/XSRF state. Neither arbitrary URLs nor JavaScript can be supplied by a server job.
- Closing the paired tab/server disconnects that route without launching a managed browser or disabling the account. The extension finds the same signed-in account's tab on restart and reconnects automatically. A new pairing rotates the key and revokes the previous connection. Credits are checked on connection; project creation and generation use the same route. An unknown balance is never presented as a verified zero.
- The connector maps fixed `error_code` values to user-facing messages. Reusing a consumed code returns `pairing_invalid`; rejected sessions, missing identities, network failures, local storage failures and verification timeouts have distinct codes. Raw Google/server exception text never reaches the extension.
- Cancel invalidates a waiting pairing; an in-flight save is allowed to finish. Closing the extension popup does not cancel server verification, and the app can observe completion through authenticated polling. The extension must be installed manually once per normal browser profile through Load unpacked. `/setup` provides the guide and `/flow-account-connector.zip` provides a fixed allowlist of extension files.

## Legacy integration (retained for compatibility)

The previous desktop flow used a local browser helper and an authenticated server handoff. The helper remains available to older callers, but is not launched by the current dashboard or desktop connection. Google may reject sign-in browsers with automation attached. Remote dashboards and Docker deployments retain manual import.

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

## Dashboard setup and portable launcher

The Accounts dashboard includes Connect Google Flow, progress, Cancel, Add another Google account, and per-account Reconnect Google. `dashboard_login.py` runs one bounded background job at a time. It reuses installed Chrome or Edge, installs managed Chromium if needed, captures a private helper result, and delegates registration to the verified session service. UUID profile mappings and the selected browser path persist under `data/browser-login/`. Deleting a dashboard account removes its profile mapping and managed profile. Account writes finish before shutdown; cancellation cannot interrupt the final save midway.

After successful registration the dashboard configures the local `personal` browser captcha method and enables automatic protocol refresh. Existing account proxy, project, model-permission, and concurrency settings are preserved. Browser warmup is deferred when the local launcher starts so that stale accounts cannot block access to the repair dashboard.

The admin-authenticated `/api/browser-login/start`, `/api/browser-login/status`, and `/api/browser-login/cancel` routes require the loopback client and a loopback Host, and reject cross-origin browser requests. Remote servers return a clear local-Windows requirement. The progress API contains status and public account metadata; it does not return the helper's cookies.

`start_local.py` creates private credentials only for a new configuration, chooses a free loopback port, starts the server, and opens `/login` with a random one-use ticket in the URL fragment. The login page immediately removes the fragment and exchanges the ticket through `/api/local-dashboard` for an HttpOnly, SameSite=Strict admin cookie. Tickets expire after three minutes, require loopback/same-origin requests, and cannot be reused. Admin credentials are neither placed in a URL nor printed by the launcher. Existing manual admin login remains available.

The portable Windows package includes the pinned Python runtime and installed dependencies, so its START launcher executes Python directly. The source bootstrap script verifies the Python download SHA-256 before extraction and installs requirements when their hash changes. It does not change PowerShell execution-policy settings.

Dashboard service, endpoint, ticket, and clean-configuration tests live in `tests/test_dashboard_login.py`. UI checks use a simulated Google login fixture; actual Google authentication and media generation still require a real account.
