"""Interactive Google Flow login helper for trusted local desktop clients.

The caller supplies an isolated profile and browser executable through the environment.
Successful output contains session credentials and must be consumed over a private pipe,
never displayed, logged, or redirected into a file. No Google password is requested here.
"""

import asyncio, json, os, re, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

def google_cookie(cookie):
    host = cookie.get('domain', '').lstrip('.')
    return (host == 'google.com' or host.endswith('.google.com')) and not cookie.get('partitionKey')

def login_executable():
    configured = os.environ['BROWSER_EXECUTABLE_PATH']
    # Managed Chrome for Testing can open a blank window on Windows. Prefer an installed
    # everyday browser for interactive Google sign-in, still with our isolated profile.
    managed = any(part.startswith('chromium-') for part in Path(configured).parts)
    if managed:
        for base in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            if not os.environ.get(base):
                continue
            for relative in ('Google/Chrome/Application/chrome.exe', 'Microsoft/Edge/Application/msedge.exe'):
                candidate = Path(os.environ[base]) / relative
                if candidate.is_file():
                    return str(candidate)
    return configured

async def main():
    async with async_playwright() as p:
        profile = Path(os.environ['BANG_LOGIN_PROFILE'])
        port_file = profile / 'DevToolsActivePort'
        port_file.unlink(missing_ok=True)
        # Launch a regular visible browser. CDP attaches only to this app-owned profile on loopback.
        process = subprocess.Popen([
            login_executable(),
            '--user-data-dir=' + str(profile), '--remote-debugging-address=127.0.0.1',
            '--remote-debugging-port=0', '--no-first-run', '--no-default-browser-check',
            'https://flow.google.com/',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = None
        try:
            port = None
            for _ in range(120):
                if process.poll() is not None:
                    return 5
                try:
                    candidate = port_file.read_text().splitlines()[0]
                    if candidate.isdigit() and 0 < int(candidate) < 65536:
                        port = candidate
                        break
                except (OSError, IndexError):
                    pass
                await asyncio.sleep(0.25)
            if not port:
                return 5
            browser = await p.chromium.connect_over_cdp('http://127.0.0.1:' + port)
            context = browser.contexts[0]
            # Some Windows browsers restore an empty initial tab instead of the command-line URL.
            if context.pages and all(page.url == 'about:blank' for page in context.pages):
                try:
                    await context.pages[0].goto('https://flow.google.com/', wait_until='domcontentloaded', timeout=30000)
                except Exception:
                    return 6
            deadline = asyncio.get_running_loop().time() + 600
            while asyncio.get_running_loop().time() < deadline:
                if not context.pages:
                    return 2
                for page in context.pages:
                    if urlparse(page.url).hostname != 'flow.google.com':
                        continue
                    try:
                        identity = await page.evaluate("({host: location.hostname, email: (window.WIZ_global_data || {}).oPEP7c || ''})")
                        email = str(identity.get('email', '')).strip().lower()
                        if identity.get('host') != 'flow.google.com' or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                            continue
                        expected = os.environ.get('BANG_LOGIN_EMAIL', '')
                        if expected and expected != email:
                            return 3
                        cookies = [c for c in await context.cookies() if google_cookie(c)]
                        names = {c['name'] for c in cookies}
                        if not names.intersection({'OSID', '__Secure-OSID'}) or not names.intersection({'SID', 'HSID', 'SSID', 'APISID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'}):
                            continue
                        print(json.dumps({'email': email, 'cookies': cookies}, separators=(',', ':')), flush=True)
                        return 0
                    except Exception:
                        if page.is_closed():
                            continue
                await asyncio.sleep(1)
            return 4
        finally:
            if browser:
                try:
                    session = await browser.new_browser_cdp_session()
                    await session.send('Browser.close')
                except Exception:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            if process.poll() is None:
                subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception:
        # Browser errors may contain URLs or session data; the parent supplies a safe error message.
        sys.exit(5)
