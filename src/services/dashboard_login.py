"""Local dashboard orchestration for interactive Google Flow account setup."""
import asyncio
import json
import os
import re
import shutil
import sys
from pathlib import Path
from uuid import UUID, uuid4


class DashboardSetupError(ValueError):
    pass


class DashboardLogin:
    def __init__(self, root=None):
        self.root = Path(root or 'data/browser-login').resolve()
        try:
            executable = json.loads((self.root / 'browser.json').read_text(encoding='utf-8'))
            if isinstance(executable, str) and Path(executable).is_file():
                os.environ.setdefault('BROWSER_EXECUTABLE_PATH', executable)
        except (OSError, ValueError):
            pass
        self.task = None
        self.process = None
        self.state = {'job_id': None, 'phase': 'idle', 'message': 'Connect your Google account to get started.', 'account': None}

    def status(self):
        return {**self.state, 'busy': bool(self.task and not self.task.done()), 'supported': sys.platform == 'win32'}

    def _report(self, phase, message, **extra):
        self.state = {**self.state, 'phase': phase, 'message': message, **extra}

    def _profiles(self):
        file = self.root / 'profiles.json'
        if not file.exists():
            return {}
        try:
            data = json.loads(file.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or any(not isinstance(email, str) or str(UUID(value)) != value for email, value in data.items()):
                raise ValueError()
            return data
        except (ValueError, TypeError, AttributeError):
            raise DashboardSetupError('Saved browser profiles could not be read. Restore profiles.json from a backup.') from None

    async def _terminate(self):
        process = self.process
        if process and process.returncode is None:
            if sys.platform == 'win32':
                killer = await asyncio.create_subprocess_exec('taskkill.exe', '/PID', str(process.pid), '/T', '/F', stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                try:
                    await asyncio.wait_for(killer.wait(), 10)
                except asyncio.TimeoutError:
                    killer.kill()
            else:
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        self.process = None

    async def _browser(self):
        candidates = [os.environ.get('BROWSER_EXECUTABLE_PATH')]
        for base in ['PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA']:
            if os.environ.get(base):
                candidates.append(str(Path(os.environ[base]) / 'Google/Chrome/Application/chrome.exe'))
                candidates.append(str(Path(os.environ[base]) / 'Microsoft/Edge/Application/msedge.exe'))
        for executable in candidates:
            if executable and Path(executable).is_file():
                return executable
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            executable = playwright.chromium.executable_path
        if not Path(executable).is_file():
            self._report('preparing', 'Installing the login browser. This may take a few minutes…')
            self.process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'playwright', 'install', 'chromium', stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            try:
                result = await asyncio.wait_for(self.process.wait(), 600)
            finally:
                await self._terminate()
            if result or not Path(executable).is_file():
                raise DashboardSetupError('Browser installation failed. Check your internet connection and click Connect again.')
        return executable

    async def _capture(self, executable, profile, email):
        env = {**os.environ, 'PYTHONUTF8': '1', 'BROWSER_EXECUTABLE_PATH': str(executable), 'BANG_LOGIN_PROFILE': str(profile), 'BANG_LOGIN_EMAIL': email or ''}
        self.process = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name('browser_login.py')), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=65536)
        async def read_result():
            output = bytearray()
            while True:
                chunk = await self.process.stdout.read(16384)
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > 524288:
                    raise DashboardSetupError('The login session could not be read. Try connecting again.')
            code = await self.process.wait()
            if code:
                messages = {2: 'The login browser was closed. Click Connect to try again.', 3: 'Reconnect with the same Google account.', 4: 'Login timed out. Click Connect to try again.'}
                raise DashboardSetupError(messages.get(code, 'The login browser could not complete setup. Try connecting again.'))
            try:
                value = json.loads(output)
                identity = value['email'].strip().lower()
                if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', identity) or not isinstance(value['cookies'], list) or not value['cookies'] or (email and identity != email):
                    raise ValueError()
                return identity, json.dumps(value['cookies'], separators=(',', ':'))
            except (ValueError, KeyError, TypeError, AttributeError):
                raise DashboardSetupError('The Flow session could not be read. Sign in again.') from None
        try:
            return await asyncio.wait_for(read_result(), 660)
        except asyncio.TimeoutError:
            raise DashboardSetupError('Login timed out. Click Connect to try again.') from None
        finally:
            await self._terminate()

    async def start(self, register, *, email=None, account_id=None):
        if sys.platform != 'win32':
            raise DashboardSetupError('Automatic dashboard login currently needs a local Windows server. Use Bang Story or manual import for other deployments.')
        if self.task and not self.task.done():
            raise DashboardSetupError('A login is already in progress. Finish it or cancel it first.')
        self.root.mkdir(parents=True, exist_ok=True)
        profiles = self._profiles()
        previous = profiles.get(email) if email else None
        directory = previous or str(uuid4())
        profile = self.root / directory
        profile.mkdir(exist_ok=True)
        self.state = {'job_id': str(uuid4()), 'phase': 'preparing', 'message': 'Preparing Google Flow login…', 'account': None}
        self.task = asyncio.create_task(self._run(register, profile, directory, previous, email, account_id))
        return self.status()

    async def _run(self, register, profile, directory, previous, email, account_id):
        saved = False
        try:
            executable = await self._browser()
            os.environ['BROWSER_EXECUTABLE_PATH'] = str(executable)
            self._report('login', 'Sign in in the browser that opened. Complete Google verification and open Flow; everything else is automatic.')
            identity, cookies = await self._capture(executable, profile, email)
            self._report('saving', 'Verifying the Google account and applying local settings…')
            result = await asyncio.wait_for(register(identity, cookies, account_id), 150)
            saved = True
            profiles = self._profiles()
            old = profiles.get(identity)
            profiles[identity] = directory
            temporary = self.root / 'profiles.json.tmp'
            temporary.write_text(json.dumps(profiles), encoding='utf-8')
            temporary.replace(self.root / 'profiles.json')
            (self.root / 'browser.json').write_text(json.dumps(str(executable)), encoding='utf-8')
            if old and old != directory:
                shutil.rmtree(self.root / old, ignore_errors=True)
            self._report('ready', 'Account connected. Local browser setup and automatic session refresh are enabled.', account=result['account'])
        except asyncio.CancelledError:
            self._report('cancelled', 'Login cancelled. You can connect again whenever you are ready.')
        except DashboardSetupError as exc:
            self._report('error', str(exc))
        except Exception:
            self._report('error', 'Setup could not finish. Check your Flow access and internet connection, then try again.')
        finally:
            await self._terminate()
            if not saved and not previous:
                shutil.rmtree(profile, ignore_errors=True)

    async def cancel(self, job_id):
        if job_id != self.state['job_id']:
            raise DashboardSetupError('This login is no longer active. Refresh the dashboard.')
        if self.state['phase'] == 'saving':
            raise DashboardSetupError('Account verification is finishing. Please wait for the result.')
        if self.task and not self.task.done():
            self.task.cancel()
            await self.task
        return self.status()

    async def close(self):
        if self.task and not self.task.done():
            if self.state['phase'] != 'saving':
                self.task.cancel()
            await self.task

    def forget(self, email):
        profiles = self._profiles()
        directory = profiles.pop(str(email or '').strip().lower(), None)
        if directory:
            shutil.rmtree(self.root / directory, ignore_errors=True)
            temporary = self.root / 'profiles.json.tmp'
            temporary.write_text(json.dumps(profiles), encoding='utf-8')
            temporary.replace(self.root / 'profiles.json')
        if (self.state.get('account') or {}).get('email') == str(email or '').strip().lower():
            self.state = {'job_id': None, 'phase': 'idle', 'message': 'Account removed. Connect another Google account whenever you are ready.', 'account': None}
