# Flow2API English

English interface and setup documentation for [TheSmallHanCat/flow2api](https://github.com/TheSmallHanCat/flow2api), maintained in [Exeloxylade/flow2api-English](https://github.com/Exeloxylade/flow2api-English).

Flow2API exposes an OpenAI-compatible API for Google Flow image and video generation using your own Google account. This community project is not an official Google API. Available models, account access, quotas, and browser requirements depend on Google Flow.

The login page, account management panel, settings, request logs, model test page, and bundled Captcha Worker settings are in English. The original upstream documentation is preserved in [README.zh-CN.md](README.zh-CN.md). The MIT license and original copyright notices are retained in [LICENSE](LICENSE).

## Use with Bang Story

Use the updated [Bang Story repository](https://github.com/Exeloxylade/Bang-Story-free-version).

1. Open **Pengaturan → Flow2API** and enable **Gunakan Flow2API lokal**.
2. Click **Pasang Flow2API**. To replace an older Chinese installation, stop it first and click **Pasang ulang**.
3. Click **Jalankan dan login**, then **Buka panel akun**. Bang Story manages the local admin login and API key.
4. Open **Setup guide** at the top of the English panel and follow the account steps below.
5. Return to Bang Story, click **Periksa akun**, then **Gunakan untuk proyek baru**. Existing projects can select Flow2API in **Ide cerita**.

Bang Story uses `http://127.0.0.1:8765`. Its local installer downloads Python and Chromium; Docker is not required. Reinstalling the server preserves its `data`, `tmp`, and `config/setting.toml` files; keep a separate backup before making other manual changes.

## Add a Google Flow account

This version uses **complete Google/Flow cookies**, not a single old Session Token/ST.

1. Sign in at `https://flow.google.com` and confirm that Flow opens for the intended account.
2. Open browser **DevTools (F12) → Network**, reload Flow, select its document request, and copy the complete **Cookie** value from **Headers → Request Headers**. JSON cookie exports containing both Flow and Google cookies are also accepted.
3. In **Accounts → Add**, paste into **Google Cookies** and enter the matching email in **Google Account**.
4. Leave project and proxy fields empty unless you need them. Click **Add** and confirm that the account is enabled.
5. If validation fails, sign in again and copy fresh, complete cookies. A working account check does not guarantee quota or successful generation.

The cookies must include a Flow session cookie (`OSID` or `__Secure-OSID`) and Google account cookies such as `SID`/`SAPISID`. An old `__Secure-next-auth.session-token` alone is insufficient.

Cookies and account export files contain sign-in credentials. Enter them only into your own server, do not commit them, and hide them in screenshots. The bundled **Captcha Worker** extension routes captcha requests; it is separate from a cookie-sync extension and does not import your account automatically.

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
