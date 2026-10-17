"""One-use local pairing for an explicit connection from the user's browser."""
import asyncio
import secrets
import time
from uuid import uuid4
from .dashboard_login import DashboardLogin, DashboardSetupError


class ExtensionLogin(DashboardLogin):
    def __init__(self, root=None):
        super().__init__(root)
        self.port = 8000
        self._token = None
        self._deadline = 0
        self._register = None
        self._email = None
        self._account_id = None

    def status(self):
        if self.state['phase'] == 'login' and time.monotonic() >= self._deadline:
            self._token = None
            self._report('error', 'Pairing expired. Click Connect to create a new code.', pairing_code=None)
        return {**self.state, 'busy': self.state['phase'] in ('login', 'saving'), 'supported': True}

    async def start(self, register, *, email=None, account_id=None):
        if self.status()['busy']:
            raise DashboardSetupError('Finish or cancel the current connection first.')
        self._token = secrets.token_hex(32)
        self._deadline = time.monotonic() + 600
        self._register, self._email, self._account_id = register, email, account_id
        self.state = {
            'job_id': str(uuid4()), 'phase': 'login', 'account': None,
            'pairing_code': f'{self.port}:{self._token}',
            'message': 'Sign in to Flow in your own browser. Paste this code into Flow Account Connector and click Connect this account. The code expires in 10 minutes.',
        }
        return self.status()

    async def submit(self, token, email, cookies):
        if not self.status()['busy'] or self.state['phase'] != 'login' or not self._token or not secrets.compare_digest(token, self._token):
            raise DashboardSetupError('Pairing code is invalid, expired, or already used. Create a new code in the app.')
        if self._email and self._email != email:
            raise DashboardSetupError('Reconnect with the same Google account.')
        # Consume before awaiting upstream I/O, so concurrent requests cannot reuse this capability.
        self._token = None
        self._report('saving', 'Verifying your Flow account…', pairing_code=None)
        self.task = asyncio.create_task(self._finish(email, cookies))
        await asyncio.shield(self.task)
        if self.state['phase'] != 'ready':
            raise DashboardSetupError(self.state['message'])
        return {'success': True, 'account': self.state['account']}

    async def _finish(self, email, cookies):
        try:
            result = await asyncio.wait_for(self._register(email, cookies, self._account_id), timeout=120)
            self._report('ready', 'Account connected. Automatic session refresh is enabled.', account=result['account'])
        except Exception:
            # Upstream exceptions can include cookies and request headers.
            self._report('error', 'Flow could not verify the session. Open Flow with the intended account, then create a new pairing code and reconnect.')
        finally:
            self._register = None

    async def cancel(self, job_id):
        if job_id != self.state['job_id']:
            raise DashboardSetupError('This connection is no longer active. Refresh the app.')
        if self.state['phase'] == 'saving':
            raise DashboardSetupError('Account verification is finishing. Please wait for the result.')
        if self.status()['phase'] != 'login':
            return self.status()
        self._token = None
        self._register = None
        self._report('cancelled', 'Connection cancelled. Your normal browser remains open.', pairing_code=None)
        return self.status()

    async def close(self):
        self._token = None
        if self.task and not self.task.done():
            await self.task
