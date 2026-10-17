# Flow2API English

English interface and setup documentation for [TheSmallHanCat/flow2api](https://github.com/TheSmallHanCat/flow2api), maintained in [Exeloxylade/flow2api-English](https://github.com/Exeloxylade/flow2api-English).

Flow2API exposes an OpenAI-compatible API for Google Flow image and video generation using your own Google account. This community project is not an official Google API. Available models, account access, quotas, and browser requirements depend on Google Flow.

The login page, account management panel, settings, request logs, model test page, and bundled Captcha Worker settings are in English. The original upstream documentation is preserved in [README.zh-CN.md](README.zh-CN.md). The MIT license and original copyright notices are retained in [LICENSE](LICENSE).

## Easy local Windows setup

1. Extract the Windows portable package and double-click **START - WIN.bat**. Keep its console window open while using Flow2API.
2. Your local dashboard opens automatically; no admin password, Python commands, Docker, or API-key configuration is needed. The portable package includes Python and server dependencies. A source checkout can prepare its runtime through the included PowerShell setup script.
3. In **Accounts**, click **Connect Google Flow**. The server uses installed Chrome or Edge, or installs its managed Chromium browser automatically.
4. Sign in directly with Google and continue until Flow opens. The dashboard registers the verified account and configures local browser generation and automatic session refresh.
5. Click **Add another Google account** for more accounts. Use **Reconnect Google** beside an existing account when it needs a fresh login.

Progress, Cancel, and Retry are built into the dashboard. Each account gets an isolated login profile. Existing server accounts and configuration are preserved; a new local installation gets private generated credentials. The launcher binds only to loopback and uses a short-lived, one-use local dashboard sign-in capability. If port 8000 is busy, it chooses an available port up to 8010 and opens the correct address for you.

Automatic browser login runs on the Windows computer hosting the server. Remote/Docker deployments keep the manual import option; opening a remote dashboard cannot launch a browser on your own computer. Google verification, Flow access, account quota, and service restrictions still apply. A successful account connection does not guarantee generation quota.

## Use with Bang Story

Use the updated [Bang Story repository](https://github.com/Exeloxylade/Bang-Story-free-version). The matching integration is proposed in [Bang Story PR #3](https://github.com/Exeloxylade/Bang-Story-free-version/pull/3).

1. Open **Pengaturan → Google Flow** and click **Hubungkan Google Flow**.
2. Bang Story installs Python, Chromium, and this server automatically when needed, then starts the local service. Docker and manual API-key setup are not required.
3. Sign in directly with Google in the browser that opens. Complete any verification and continue until Google Flow opens. Bang Story captures the session over a private pipe and sends it to the authenticated local registration endpoint.
4. The server verifies the signed-in identity against Google Flow before adding or updating the account. Successful connection selects Flow for images and videos in new Bang Story projects.
5. Click **Tambah akun Google** for another account. Use **Hubungkan ulang** or **Hapus** in the account list. Each account has an isolated login profile; reconnecting with a different identity is rejected.

Bang Story uses `http://127.0.0.1:8765`. If you already have an older local server installation, stop it and choose **Pengaturan lanjutan → Pasang ulang** to obtain the new login helper and registration API. Updating the desktop app alone does not replace server files. Reinstallation preserves `data`, `tmp`, and `config/setting.toml`.

Browser/API tests use test doubles. Live Google authentication, account eligibility, quota, and generation still require account-level testing; Google may require verification or a fresh login.

### Shared desktop login integration

This fork now owns `src/services/browser_login.py`, the Windows browser-login helper used by Bang Story, and `POST /api/tokens/browser-session`, the admin-authenticated session handoff. Registration verifies the Flow account identity, updates duplicate emails, validates reconnect targets, and re-enables a previously disabled account only after validation. The response contains account metadata and no cookies or access tokens. See [the desktop integration contract](docs/desktop-login.md).

## Add an account manually (advanced / standalone)

Standalone server users can continue to use **Accounts → Add**. This fallback is also available in Bang Story's advanced panel; it is not required for the automatic desktop login.

1. Sign in at `https://flow.google.com` and confirm that Flow opens for the intended account.
2. In browser **DevTools (F12) → Network**, reload Flow, select its document request, and copy the complete **Cookie** value from **Headers → Request Headers**. JSON exports containing Flow and Google cookies are also accepted.
3. In **Accounts → Add**, paste into **Google Cookies**, enter the matching email in **Google Account**, and save. Leave project and proxy fields empty unless needed.

Cookies must include a Flow session cookie (`OSID` or `__Secure-OSID`) and Google account cookies such as `SID`/`SAPISID`. An old `__Secure-next-auth.session-token` alone is insufficient.

Cookies and account exports grant access to sign-in sessions. Keep them on your own server, out of commits, logs, screenshots, and support messages. Session cookies remain stored by the local browser and upstream database; this integration does not add database encryption. The Captcha Worker extension handles captcha requests and is separate from account login.

## Standalone Windows setup

Use Python 3.10 or newer. Python 3.12 is used by the Bang Story integration.

```powershell
git clone https://github.com/Exeloxylade/flow2api-English.git
cd flow2api-English
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config/setting_example.toml config/setting.toml
```

Before starting, edit `config/setting.toml`: set a private API key, your own admin username/password, and `server.host = "127.0.0.1"` for a local-only server. The example contains placeholder credentials; do not expose it as-is. For browser mode, install Chromium with:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe main.py
```

Open `http://127.0.0.1:8000`, sign in with the admin credentials you configured, and select **Setup guide**. In **Settings → Captcha settings**, choose the browser/service method appropriate for your deployment. Bang Story local mode selects its built-in browser method automatically.

For a server you manage separately, enter its URL and **Flow2API API key** in Bang Story. This is not a Gemini API key or Google cookie.

## Test and connect

- **Accounts**: add, edit, enable, disable, import, and export accounts.
- **Settings**: API key, admin password, proxies, generation timeouts, cache, and captcha/browser options.
- **Test page**: enter the server API key, select an image model, and generate a small test.
- **Request logs**: inspect request status and errors.
- **Setup guide**: available locally at `/setup`, including before signing in.

API clients use `Authorization: Bearer <your-api-key>`:

```text
GET  /v1/models
POST /v1/chat/completions
```

Use a model ID returned by `/v1/models`; supported IDs can change. For request examples, Docker deployments, model details, and advanced configuration, consult the preserved [upstream reference](README.zh-CN.md). Docker images named in the upstream reference belong to upstream and may still use its Chinese interface; build this fork's source for English pages.

## Troubleshooting

| Problem | What to check |
|---|---|
| Panel remains Chinese | Update Bang Story, stop Flow2API, choose **Pasang ulang**, and start again. |
| Missing Google Cookies | Copy complete current cookies for Flow and the Google account; do not use only an old ST. |
| Account email mismatch | Sign in with the matching account and refresh its cookies. |
| API returns 401 | Use the server API key, not the admin password, cookies, or Gemini key. |
| Account connected, generation fails | Check Flow access, quota, model ID, browser/captcha status, and request logs. |
| Standalone port differs | Standalone defaults to 8000; Bang Story local mode uses 8765. |

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall -q src
```

UI translation changes preserve API field names, model IDs, authentication behavior, and account data. Browser automation still depends on an active Google session and upstream behavior; local tests do not establish that live generation works for every account.
