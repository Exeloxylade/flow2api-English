"""One-use local pairing for an explicit connection from the user's browser."""
import asyncio
import secrets
import time
from uuid import uuid4
from .dashboard_login import DashboardLogin, DashboardSetupError
from .browser_accounts import BrowserSessionError


CONNECTION_ERRORS = {
    'pairing_invalid': 'The pairing code is expired, cancelled, or already used. Copy a new code from the app before clicking Connect again.',
    'account_mismatch': 'The server sees a different Google account. Use a browser profile signed in to the intended Flow account.',
    'cookies_incomplete': 'The Flow session is incomplete. Open the signed-in Flow studio before reconnecting.',
    'flow_signin_redirect': 'Google redirected the server to sign-in. The transferred session was not accepted; this is not an expired pairing code.',
    'flow_http_error': 'Google Flow rejected the server verification request. Check Flow access and the server network.',
    'flow_frontend_changed': 'Google Flow returned an unexpected page. Flow2API needs a frontend compatibility update.',
    'flow_identity_missing': 'The server could not find a signed-in identity in the Flow page. Open the creative studio and reconnect.',
    'flow_network_error': 'Flow2API could not reach Google Flow. Check the server internet connection or proxy.',
    'account_save_failed': 'The verified account could not be saved locally. Check disk space and retry.',
    'account_verification_failed': 'Google Flow could not verify the session. Open the intended Flow studio and create a fresh pairing code.',
    'verification_timeout': 'The server timed out while verifying Flow. Check its network and create a new code.',
    'account_setup_failed': 'Account setup failed after pairing. Create a fresh code and check the local server configuration.',
    'local_configuration_failed': 'The account was saved, but local generation settings could not be updated. Restart the service and check the account list.',
}


class ExtensionConnectionError(DashboardSetupError):
    def __init__(self, code):
        self.code = code if code in CONNECTION_ERRORS else 'account_setup_failed'
        super().__init__(CONNECTION_ERRORS[self.code])


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
            self._report('error', 'Pairing expired. Click Connect to create a new code.', pairing_code=None, error_code='pairing_invalid')
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
            raise ExtensionConnectionError('pairing_invalid')
        if self._email and self._email != email:
            raise ExtensionConnectionError('account_mismatch')
        # Consume before awaiting upstream I/O, so concurrent requests cannot reuse this capability.
        self._token = None
        self._report('saving', 'Verifying your Flow account…', pairing_code=None)
        self.task = asyncio.create_task(self._finish(email, cookies))
        await asyncio.shield(self.task)
        if self.state['phase'] != 'ready':
            raise ExtensionConnectionError(self.state.get('error_code', 'account_setup_failed'))
        return {'success': True, 'account': self.state['account']}

    async def _finish(self, email, cookies):
        try:
            result = await asyncio.wait_for(self._register(email, cookies, self._account_id), timeout=120)
            self._report('ready', 'Account connected. Automatic session refresh is enabled.', account=result['account'])
        except Exception as exc:
            # Only fixed categories cross the local API; never expose exception text.
            code = exc.code if isinstance(exc, BrowserSessionError) else 'verification_timeout' if isinstance(exc, asyncio.TimeoutError) else 'account_setup_failed'
            error = ExtensionConnectionError(code)
            self._report('error', str(error), error_code=error.code)
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
