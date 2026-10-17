"""Use the real registration manager and SQLite, mocking only Google's verifier/RPCs."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from src.core.database import Database
from src.services.token_manager import TokenManager
from src.services.browser_accounts import register_browser_session, BrowserSessionError
from src.services import browser_accounts

EMAIL = 'owner@example.com'
COOKIES = json.dumps([{'name': 'OSID', 'value': 'fake-flow', 'domain': 'flow.google.com', 'path': '/'}, {'name': 'SID', 'value': 'fake-google', 'domain': '.google.com', 'path': '/'}])


class VerifiedAccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_binding_hash_is_persisted_and_live_pairing_does_not_validate_copied_cookies(self):
        result = await self.connect(trust_browser_identity=True, live_browser=True)
        self.verify.assert_not_awaited()
        account_id = result['account']['id']
        await self.db.update_token(account_id, browser_bridge_hash='hash-only')
        self.assertEqual((await self.db.get_token(account_id)).browser_bridge_hash, 'hash-only')

    async def asyncSetUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.db = Database(str(Path(folder.name)/'flow.db'))
        await self.db.init_db()
        self.flow = AsyncMock()
        for name in ('st_to_at', 'get_credits', 'create_project'):
            getattr(self.flow, name).side_effect = RuntimeError('RPC unavailable with private-cookie-data')
        self.manager = TokenManager(self.db, self.flow)
        verifier = patch.object(browser_accounts.protocol_loginer, 'login', AsyncMock(return_value={'success': True, 'email': EMAIL, 'google_cookies': COOKIES}))
        self.verify = verifier.start(); self.addCleanup(verifier.stop)

    async def connect(self, **kwargs):
        return await register_browser_session(self.manager, self.db, email=EMAIL, google_cookies=COOKIES, **kwargs)

    async def test_verified_account_is_saved_even_when_credits_and_project_rpcs_are_unavailable(self):
        result = await self.connect()
        self.assertTrue(result['success'])
        account = await self.db.get_token_by_email(EMAIL)
        self.assertTrue(account.is_active)
        self.assertEqual(account.google_cookies, COOKIES)
        self.assertEqual(account.at, 'flow-frontend-cookie')
        self.assertIsNone(account.current_project_id)
        for name in ('st_to_at', 'get_credits', 'create_project'): getattr(self.flow, name).assert_not_awaited()
        self.assertEqual(await self.db.get_projects_by_token(account.id), [])

    async def test_project_failure_occurs_on_first_use_and_keeps_the_connected_account(self):
        result = await self.connect()
        with self.assertRaises(ValueError): await self.manager.ensure_project_exists(result['account']['id'])
        self.flow.create_project.assert_awaited_once()
        self.assertTrue((await self.db.get_token(result['account']['id'])).is_active)

    async def test_duplicate_reconnect_updates_and_reenables_without_generation_rpcs(self):
        first = await self.connect()
        token_id = first['account']['id']
        await self.db.update_token(token_id, is_active=False, image_enabled=False, proxy_url='http://localhost:8001')
        result = await self.connect(expected_account_id=token_id)
        saved = await self.db.get_token(token_id)
        self.assertEqual(result['action'], 'updated')
        self.assertTrue(saved.is_active)
        self.assertFalse(saved.image_enabled)
        self.assertEqual(saved.proxy_url, 'http://localhost:8001')
        self.assertEqual(len(await self.db.get_all_tokens()), 1)
        self.flow.st_to_at.assert_not_awaited()
        self.flow.create_project.assert_not_awaited()

    async def test_google_identity_verification_is_still_required_before_any_save(self):
        self.verify.return_value = {'success': False, 'error_code': 'flow_signin_redirect', 'error': 'private-cookie-data'}
        with self.assertRaises(BrowserSessionError) as error: await self.connect()
        self.assertEqual(error.exception.code, 'flow_signin_redirect')
        self.assertNotIn('private-cookie-data', str(error.exception))
        self.assertEqual(await self.db.get_all_tokens(), [])
