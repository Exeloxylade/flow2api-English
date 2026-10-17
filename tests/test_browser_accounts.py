"""Regression tests for the authenticated desktop browser-session handoff."""
import asyncio
import json
import types
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from src.api import admin
from src.services import browser_accounts

EMAIL = 'owner@example.com'
COOKIES = json.dumps([
    {'name': 'OSID', 'value': 'session', 'domain': 'flow.google.com', 'path': '/'},
    {'name': 'SID', 'value': 'account', 'domain': '.google.com', 'path': '/'},
])

def account(id=7, email=EMAIL, active=True):
    return types.SimpleNamespace(id=id, email=email, login_account=email, st='private-st', is_active=active, image_concurrency=2, video_concurrency=1, proxy_url=None)

class BrowserSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = types.SimpleNamespace(
            get_token=AsyncMock(return_value=account()), save_verified_browser_account=AsyncMock(return_value=account()),
            update_token=AsyncMock(), enable_token=AsyncMock(),
            flow_client=types.SimpleNamespace(st_to_at=AsyncMock(return_value={'access_token': 'private-at', 'expires': '2026-12-01T00:00:00Z'})),
        )
        self.db = types.SimpleNamespace(get_token_by_email=AsyncMock(return_value=None))
        self.concurrency = types.SimpleNamespace(reset_token=AsyncMock())
        verifier = patch.object(browser_accounts.protocol_loginer, 'login', AsyncMock(return_value={'success': True, 'email': EMAIL, 'google_cookies': COOKIES}))
        self.login = verifier.start()
        self.addCleanup(verifier.stop)
        for name, value in [('token_manager', self.manager), ('db', self.db), ('concurrency_manager', self.concurrency), ('browser_registration_lock', asyncio.Lock())]:
            patcher = patch.object(admin, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.auth = 'test-private-admin'
        admin.active_admin_tokens.add(self.auth)
        self.addCleanup(admin.active_admin_tokens.discard, self.auth)
        app = FastAPI()
        app.include_router(admin.router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver')
        self.addAsyncCleanup(self.client.aclose)

    async def connect(self, **overrides):
        return await self.client.post('/api/tokens/browser-session', headers={'Authorization': 'Bearer ' + self.auth}, json={'login_account': EMAIL, 'google_cookies': COOKIES, **overrides})

    async def test_add_verifies_identity_and_returns_no_credentials(self):
        response = await self.connect()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'success': True, 'action': 'added', 'account': {'id': 7, 'email': EMAIL, 'enabled': True}})
        self.login.assert_awaited_once_with(COOKIES, proxy=None, email=EMAIL)
        self.manager.save_verified_browser_account.assert_awaited_once()
        self.concurrency.reset_token.assert_awaited_once_with(7, image_concurrency=2, video_concurrency=1)
        self.assertNotIn('private-', response.text)
        self.assertNotIn('google_cookies', response.text)

    async def test_duplicate_email_updates_instead_of_adding(self):
        self.db.get_token_by_email.return_value = account()
        response = await self.connect(login_account=' OWNER@EXAMPLE.COM ')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['action'], 'updated')
        self.manager.save_verified_browser_account.assert_awaited_once()
        self.assertEqual(self.manager.save_verified_browser_account.await_args.args, (EMAIL, COOKIES))
        self.assertEqual(self.manager.save_verified_browser_account.await_args.kwargs["existing"].id, 7)

    async def test_reconnect_reenables_account_after_validation(self):
        self.db.get_token_by_email.return_value = account(active=False)
        response = await self.connect(expected_account_id=7)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.manager.save_verified_browser_account.await_args.kwargs["existing"].is_active)

    async def test_wrong_reconnect_identity_is_rejected_before_network_or_writes(self):
        self.manager.get_token.return_value = account(email='different@example.com')
        response = await self.connect(expected_account_id=7)
        self.assertEqual(response.status_code, 400)
        self.login.assert_not_awaited()
        self.manager.save_verified_browser_account.assert_not_awaited()
        self.manager.update_token.assert_not_awaited()

    async def test_deleted_reconnect_target_cannot_create_replacement_account(self):
        self.manager.get_token.return_value = None
        self.assertEqual((await self.connect(expected_account_id=7)).status_code, 400)
        self.manager.save_verified_browser_account.assert_not_awaited()

    async def test_server_observed_identity_must_match_client_claim(self):
        self.login.return_value = {'success': True, 'email': 'different@example.com', 'google_cookies': COOKIES}
        self.assertEqual((await self.connect()).status_code, 400)
        self.manager.save_verified_browser_account.assert_not_awaited()

    async def test_expired_login_errors_are_sanitized(self):
        self.login.return_value = {'success': False, 'error': 'private-cookie-value'}
        response = await self.connect()
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('private-cookie-value', response.text)
        self.manager.save_verified_browser_account.assert_not_awaited()

    async def test_upstream_exception_never_leaks_cookie_value(self):
        self.manager.save_verified_browser_account.side_effect = RuntimeError('private-cookie-value')
        response = await self.connect()
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('private-cookie-value', response.text)

    async def test_incomplete_verified_cookies_cannot_be_saved(self):
        self.login.return_value = {'success': True, 'email': EMAIL, 'google_cookies': 'SID=only'}
        self.assertEqual((await self.connect()).status_code, 400)
        self.manager.save_verified_browser_account.assert_not_awaited()

    async def test_admin_session_is_required(self):
        body = {'login_account': EMAIL, 'google_cookies': COOKIES}
        response = await self.client.post('/api/tokens/browser-session', json=body)
        self.assertEqual(response.status_code, 401)
        self.login.assert_not_awaited()
        response = await self.client.post('/api/tokens/browser-session', headers={'Authorization': 'Bearer server-api-key'}, json=body)
        self.assertEqual(response.status_code, 401)

    async def test_request_rejects_unknown_fields_invalid_email_and_invalid_id(self):
        for overrides in [{'login_account': 'invalid'}, {'expected_account_id': -1}, {'expected_account_id': True}, {'password': 'do-not-accept'}]:
            response = await self.connect(**overrides)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn('do-not-accept', response.text)
        self.login.assert_not_awaited()

    async def test_validation_errors_never_echo_cookie_input(self):
        response = await self.connect(google_cookies=[{'name': 'OSID', 'value': 'private-cookie-value'}])
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('private-cookie-value', response.text)

    async def test_parallel_logins_for_same_email_add_only_one_account(self):
        saved = []
        async def lookup(email): return saved[0] if saved else None
        async def add(email, cookies, existing=None):
            await asyncio.sleep(0.01)
            if not existing: saved.append(account())
            return saved[0]
        self.db.get_token_by_email.side_effect = lookup
        self.manager.save_verified_browser_account.side_effect = add
        responses = await asyncio.gather(self.connect(), self.connect())
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(self.manager.save_verified_browser_account.await_count, 2)
        self.assertEqual(len(saved), 1)

if __name__ == '__main__':
    unittest.main()
