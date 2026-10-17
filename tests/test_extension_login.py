import asyncio
import json
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from src.api import admin
from src.services.extension_login import ExtensionLogin, DashboardSetupError

EMAIL = 'owner@example.com'
RESULT = {'success': True, 'account': {'id': 3, 'email': EMAIL, 'enabled': True}}


class ExtensionPairingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.service = ExtensionLogin(folder.name)
        self.register = AsyncMock(return_value=RESULT)
        self.addAsyncCleanup(self.service.close)

    async def start(self, **kwargs):
        state = await self.service.start(self.register, **kwargs)
        return state['pairing_code'].split(':')[1]

    async def test_explicit_one_use_pairing_registers_without_launching_browser(self):
        with patch('asyncio.create_subprocess_exec', side_effect=AssertionError('No browser process permitted')):
            token = await self.start()
            self.assertTrue(self.service.status()['busy'])
            result = await self.service.submit(token, EMAIL, 'private-cookies')
        self.assertEqual(result, RESULT)
        self.register.assert_awaited_once_with(EMAIL, 'private-cookies', None)
        self.assertFalse(self.service.status()['busy'])
        self.assertNotIn('private-cookies', json.dumps(self.service.status()))
        self.assertIsNone(self.service.status().get('pairing_code'))
        with self.assertRaises(DashboardSetupError):
            await self.service.submit(token, EMAIL, 'private-cookies')

    async def test_cancel_expire_restart_and_wrong_codes(self):
        token = await self.start()
        with self.assertRaises(DashboardSetupError): await self.service.submit('x' * 64, EMAIL, 'secret')
        await self.service.cancel(self.service.status()['job_id'])
        with self.assertRaises(DashboardSetupError): await self.service.submit(token, EMAIL, 'secret')
        token = await self.start()
        self.service._deadline = time.monotonic() - 1
        self.assertEqual(self.service.status()['phase'], 'error')
        with self.assertRaises(DashboardSetupError): await self.service.submit(token, EMAIL, 'secret')
        await self.start()
        self.register.assert_not_awaited()

    async def test_reconnect_is_bound_to_expected_identity(self):
        token = await self.start(email=EMAIL, account_id=3)
        with self.assertRaises(DashboardSetupError): await self.service.submit(token, 'other@example.com', 'secret')
        self.register.assert_not_awaited()
        await self.service.submit(token, EMAIL, 'secret')
        self.assertEqual(self.register.await_args.args[2], 3)

    async def test_concurrent_replay_and_cancellation_cannot_interrupt_saving(self):
        started, finish = asyncio.Event(), asyncio.Event()
        async def register(*args):
            started.set()
            await finish.wait()
            return RESULT
        token = (await self.service.start(register))['pairing_code'].split(':')[1]
        job = asyncio.create_task(self.service.submit(token, EMAIL, 'secret'))
        await started.wait()
        with self.assertRaises(DashboardSetupError): await self.service.submit(token, EMAIL, 'secret')
        with self.assertRaises(DashboardSetupError): await self.service.cancel(self.service.state['job_id'])
        finish.set()
        await job
        await self.service.cancel(self.service.state['job_id'])
        self.assertEqual(self.service.status()['phase'], 'ready')

    async def test_upstream_failures_are_sanitized_and_consume_code(self):
        self.register.side_effect = RuntimeError('private-cookies Bearer private-key')
        token = await self.start()
        with self.assertRaises(DashboardSetupError) as error: await self.service.submit(token, EMAIL, 'private-cookies')
        self.assertNotIn('private-', str(error.exception) + json.dumps(self.service.status()))
        with self.assertRaises(DashboardSetupError): await self.service.submit(token, EMAIL, 'private-cookies')


class ExtensionApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = ExtensionLogin()
        for name, value in [('dashboard_login', self.service)]:
            p = patch.object(admin, name, value); p.start(); self.addCleanup(p.stop)
        self.register = AsyncMock(return_value=RESULT)
        self.code = (await self.service.start(self.register))['pairing_code'].split(':')[1]
        app = FastAPI(); app.include_router(admin.router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8000')
        self.addAsyncCleanup(self.client.aclose)
        self.addAsyncCleanup(self.service.close)
        self.headers = {'Origin': 'chrome-extension://' + 'a'*32, 'Authorization': 'Bearer ' + self.code, 'X-Flow-Connector': '1'}
        self.body = {'login_account': EMAIL, 'google_cookies': 'private-cookies'}

    async def test_extension_pairing_needs_no_admin_cookie_but_is_one_use(self):
        response = await self.client.post('/api/browser-login/extension', headers=self.headers, json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('private-', response.text)
        response = await self.client.post('/api/browser-login/extension', headers=self.headers, json=self.body)
        self.assertEqual(response.status_code, 409)

    async def test_foreign_or_missing_origins_and_rebinding_hosts_are_denied(self):
        for origin in ['https://flow.google.com', 'https://attacker.example', 'chrome-extension://invalid']:
            response = await self.client.post('/api/browser-login/extension', headers={**self.headers, 'Origin': origin}, json=self.body)
            self.assertEqual(response.status_code, 403)
        response = await self.client.post('/api/browser-login/extension', headers={**self.headers, 'Host': 'attacker.example'}, json=self.body)
        self.assertEqual(response.status_code, 403)
        self.register.assert_not_awaited()

    async def test_originless_extension_needs_explicit_header_and_one_use_secret(self):
        response = await self.client.post('/api/browser-login/extension', headers={'Authorization': self.headers['Authorization']}, json=self.body)
        self.assertEqual(response.status_code, 403)
        response = await self.client.post('/api/browser-login/extension', headers={'Authorization': self.headers['Authorization'], 'X-Flow-Connector': '1'}, json=self.body)
        self.assertEqual(response.status_code, 200, response.text)

    async def test_invalid_auth_and_payload_never_echo_cookie_input(self):
        response = await self.client.post('/api/browser-login/extension', headers={'Origin': self.headers['Origin'], 'X-Flow-Connector': '1'}, json=self.body)
        self.assertEqual(response.status_code, 401)
        response = await self.client.post('/api/browser-login/extension', headers=self.headers, json={**self.body, 'login_account': 'private-cookies'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('private-cookies', response.text)
        response = await self.client.post('/api/browser-login/extension', headers=self.headers, json={**self.body, 'expected_account_id': 99})
        self.assertEqual(response.status_code, 422)
        self.register.assert_not_awaited()
