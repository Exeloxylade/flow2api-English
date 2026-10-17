# Flow2API English

English interface and setup documentation for [TheSmallHanCat/flow2api](https://github.com/TheSmallHanCat/flow2api), maintained in [Exeloxylade/flow2api-English](https://github.com/Exeloxylade/flow2api-English).

Flow2API exposes an OpenAI-compatible API for Google Flow image and video generation using your own Google account. This community project is not an official Google API. Available models, account access, quotas, and browser requirements depend on Google Flow.

The login page, account management panel, settings, request logs, model test page, and bundled Captcha Worker settings are in English. The original upstream documentation is preserved in [README.zh-CN.md](README.zh-CN.md). The MIT license and original copyright notices are retained in [LICENSE](LICENSE).

## Easy local Windows setup

1. Extract the Windows portable package and double-click **START - WIN.bat**. Keep its console window open while using Flow2API.
2. Your local dashboard opens automatically; no admin password, Python commands, Docker, or API-key configuration is needed. The portable package includes Python and server dependencies. A source checkout can prepare its runtime through the included PowerShell setup script.
3. Open **Install connector / guide** in the dashboard. Download and extract Flow Account Connector, then load its folder once through **edge://extensions** or **chrome://extensions → Developer mode → Load unpacked**.
4. Click **Connect Google Flow** and copy the one-use pairing code. Sign in to Flow normally in your own browser profile and enter the creative studio. Open the connector extension on that tab, paste the code, and click **Connect this account**. Keep the popup open until verification completes.
5. Click **Add another Google account** for more accounts. Use **Reconnect Google** beside an existing account when it needs a fresh login.

Progress, Cancel, and Retry are built into the dashboard. Use each account’s own Chrome/Edge profile and install the connector once in each profile. Existing server accounts and configuration are preserved; a new local installation gets private generated credentials. The launcher binds only to loopback and uses a short-lived, one-use local dashboard sign-in capability. If port 8000 is busy, it chooses an available port up to 8010 and opens the correct address for you.

The connector sends Google session cookies only after your explicit click, directly to a paired loopback server on this computer. It does not attach debugging or automation to Google sign-in. A pairing code expires after 10 minutes and can be submitted once. The browser extension is a local developer package, not a published store listing. Remote/Docker deployments keep the manual import option; opening a remote dashboard cannot launch a browser on your own computer. Google verification, Flow access, account quota, and service restrictions still apply. A successful account connection does not guarantee generation quota.

## Use with Bang Story

Use the updated [Bang Story repository](https://github.com/Exeloxylade/Bang-Story-free-version). Earlier integration work is documented in [Bang Story PR #3](https://github.com/Exeloxylade/Bang-Story-free-version/pull/3).

1. Open **Pengaturan → Google Flow** and click **Hubungkan Google Flow**.
2. Bang Story installs Python, Chromium, and this server automatically when needed, then starts the local service. Docker and manual API-key setup are not required.
3. Click **Pasang extension / panduan** for the one-time connector installation. Copy Bang Story’s pairing code, open your normal signed-in Flow studio tab, then use the extension’s **Connect this account** button. Session cookies go directly from the browser to the paired local server; they do not pass through Bang Story’s renderer or main process.
4. The server verifies the signed-in identity against Google Flow before adding or updating the account. Successful connection selects Flow for images and videos in new Bang Story projects.
5. Click **Tambah akun Google** for another account. Use **Hubungkan ulang** or **Hapus** in the account list. Use a separate normal browser profile for each account; reconnecting with a different identity is rejected.

Bang Story uses `http://127.0.0.1:8765`. If you already have an older local server installation, stop it and choose **Pengaturan lanjutan → Pasang ulang** to obtain the connector and pairing API. Updating the desktop app alone does not replace server files. Reinstallation preserves `data`, `tmp`, and `config/setting.toml`.

Browser/API tests use test doubles. Live Google authentication, account eligibility, quota, and generation still require account-level testing; Google may require verification or a fresh login.

### Shared desktop login integration

The default connection uses `browser-extension/` and `src/services/extension_login.py`. Admin-authenticated `/api/browser-login/start` creates a one-use local pairing; `/api/browser-login/extension` accepts the explicitly shared session. The older `browser_login.py` helper and `/api/tokens/browser-session` endpoint remain for compatibility, but the dashboard and updated Bang Story no longer launch the automated login helper. Registration verifies the Flow account identity, updates duplicate emails, validates reconnect targets, and re-enables a previously disabled account only after validation. The response contains account metadata and no cookies or access tokens. See [the desktop integration contract](docs/desktop-login.md).

### Keep the paired browser connected

For local browser pairing, use **Flow Account Connector 1.1.3** from the dashboard's connector download. Reload the extension after updating its files in the same folder. Only upgrades from 1.0.x need a fresh pairing; 1.1.x pairings remain valid. Keep each account's signed-in Flow studio tab open (use a separate Chrome/Edge profile per account). The panel displays **Browser online/offline**. Credit checks, project creation, CAPTCHA and image generation execute inside that exact tab and verify its account identity before each request. Server/browser restarts reconnect automatically when the matching Flow tab is open; a disconnected tab does not launch a different browser or disable its account. A pairing key is saved in extension-local storage; its hash is stored by the local server.

## CAPTCHA provider selection

In Settings → Captcha settings, **Automatic** uses each paired account's Flow tab. Accounts without a pairing keep their configured legacy provider, shown below the selector. This also preserves the behavior of existing paired accounts during upgrade.

Selecting **Built-in browser**, **Headed browser**, **Upstream Captcha Worker**, or an external provider explicitly routes CAPTCHA through that upstream handler, even for paired accounts. Account login and image RPC transport stay paired to the original account. Managed browser methods may open another browser, and the upstream Captcha Worker opens its own background tab; they are separate from Flow Account Connector. External providers require their own credentials. Google verification and token acceptance still apply.

Bang Story and new account pairing preserve this choice. Save **Automatic** to return to the paired-tab default. Standalone score testing is unavailable for paired-tab CAPTCHA and does not launch a browser for that mode. No connector reinstall is required for this server-side routing update.

## Add an account manually (advanced / standalone)

Standalone server users can continue to use **Accounts → Add**. This fallback is also available in Bang Story's advanced panel; it is not required for extension pairing.

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
