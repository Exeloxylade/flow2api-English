import asyncio
import json
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from src.api import admin

from src.core.models import Token
from src.services.browser_bridge import BrowserBridge, browser_bridge
from src.services.flow_client import FlowClient
from src.services.token_manager import TokenManager


class BrowserBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_captcha_failure_categories_have_safe_actionable_messages(self):
        for code, expected in [('captcha_native_reload_required', 'startup integration'),
                               ('captcha_script_failed', 'library could not load'),
                               ('captcha_script_policy', 'security policy'),
                               ('captcha_library_unavailable', 'public API'),
                               ('captcha_timeout', 'did not finish'),
                               ('captcha_rejected', 'API rejected'),
                               ('request_failed', 'captcha/request_failed'),
                               ('private browser exception', 'captcha/unknown_error'),
                               (['unexpected payload'], 'captcha/unknown_error')]:
            bridge = BrowserBridge()
            socket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
            await bridge.attach(1, socket)
            request = asyncio.create_task(bridge.call(1, 'a@example.com', 'captcha'))
            await asyncio.sleep(0)
            job = socket.send_json.call_args.args[0]
            bridge.receive(socket, {'req_id': job['req_id'], 'success': False,
                                    'error_code': code, 'message': 'private details'})
            with self.assertRaisesRegex(RuntimeError, expected) as error:
                await request
            self.assertNotIn('private details', str(error.exception))
            self.assertNotIn('private browser exception', str(error.exception))
            self.assertFalse(bridge.pending)

    async def test_rpc_budget_and_timeout_message_preserve_unknown_outcome(self):
        bridge = BrowserBridge()
        socket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
        await bridge.attach(1, socket)
        request = asyncio.create_task(bridge.call(1, 'a@example.com', 'rpc', timeout=10))
        await asyncio.sleep(0)
        job = socket.send_json.call_args.args[0]
        self.assertEqual(job['timeout_ms'], 10000)
        bridge.receive(socket, {'req_id': job['req_id'], 'success': False,
                                'error_code': 'request_timeout', 'message': 'private data'})
        with self.assertRaisesRegex(RuntimeError, 'outcome is unknown') as error:
            await request
        self.assertIn('[rpc/request_timeout]', str(error.exception))
        self.assertNotIn('private data', str(error.exception))
        self.assertFalse(bridge.pending)

    async def test_two_accounts_dispatch_only_to_their_own_socket(self):
        bridge = BrowserBridge()
        a = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
        b = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
        await bridge.attach(1, a)
        await bridge.attach(2, b)
        request = asyncio.create_task(bridge.call(2, 'b@example.com', 'rpc', rpc_id='nzlxg'))
        await asyncio.sleep(0)
        job = b.send_json.call_args.args[0]
        self.assertEqual(job['email'], 'b@example.com')
        bridge.receive(a, {'req_id': job['req_id'], 'success': True, 'result': 'wrong-account'})
        self.assertFalse(request.done())
        bridge.receive(b, {'req_id': job['req_id'], 'success': True, 'result': 42})
        self.assertEqual(await request, 42)
        self.assertEqual(a.send_json.await_count, 1)  # ready only

    async def test_disconnect_fails_request_and_reconnect_reuses_account(self):
        bridge = BrowserBridge()
        socket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
        await bridge.attach(1, socket)
        request = asyncio.create_task(bridge.call(1, 'a@example.com', 'rpc'))
        await asyncio.sleep(0)
        bridge.detach(1, socket)
        with self.assertRaisesRegex(RuntimeError, 'disconnected'):
            await request
        self.assertFalse(bridge.is_online(1))
        await bridge.attach(1, socket)
        self.assertTrue(bridge.is_online(1))

    async def test_credit_and_captcha_use_the_paired_tab_without_server_cookie_transport(self):
        token = Token(id=7, st='frontend-marker', email='a@example.com', browser_bridge_hash='hash')
        db = SimpleNamespace(get_token=AsyncMock(return_value=token))
        flow = FlowClient(None, db)
        flow._call_flow_frontend_rpc = AsyncMock(side_effect=AssertionError('server transport used'))
        frames = json.dumps([['wrb.fr', 'nzlxg', json.dumps([42])]])
        with patch.object(browser_bridge, 'call', AsyncMock(side_effect=[{'text': frames}, {'token': 'captcha'}])) as call:
            result = await flow.get_credits('marker', token_id=7)
            captcha, _ = await flow._get_recaptcha_token('project', token_id=7)
        self.assertEqual(result['credits'], 42)
        self.assertEqual(captcha, 'captcha')
        self.assertEqual([c.args[:3] for c in call.await_args_list], [(7, 'a@example.com', 'rpc'), (7, 'a@example.com', 'captcha')])
        flow._call_flow_frontend_rpc.assert_not_awaited()

    async def test_refresh_failure_never_launches_another_browser_or_disables_bridge_account(self):
        token = Token(id=7, st='frontend-marker', email='a@example.com', browser_bridge_hash='hash')
        db = SimpleNamespace(get_token=AsyncMock(return_value=token), update_token=AsyncMock())
        manager = TokenManager(db, None)
        manager._do_refresh_at = AsyncMock(return_value=False)
        manager._try_refresh_st = AsyncMock()
        manager.disable_token = AsyncMock()
        self.assertFalse(await manager._refresh_at_inner(7))
        manager._try_refresh_st.assert_not_awaited()
        manager.disable_token.assert_not_awaited()

    async def test_project_creation_preserves_account_id(self):
        flow = FlowClient(None)
        flow._current_rpc = AsyncMock(return_value=[])
        flow._extract_flow_project_id = lambda _: 'project-id'
        self.assertEqual(await flow.create_project('marker', 'project', token_id=7), 'project-id')
        self.assertEqual(flow._current_rpc.await_args.kwargs['token_id'], 7)

    async def test_image_failure_does_not_enter_managed_browser_recovery_or_repeat_submission(self):
        token = Token(id=7, st='marker', email='a@example.com', browser_bridge_hash='hash')
        flow = FlowClient(None, SimpleNamespace(get_token=AsyncMock(return_value=token)))
        flow._frontend_cookie = AsyncMock(return_value='cookies')
        flow._resolve_flow_frontend_cookie_storage = AsyncMock(return_value='')
        flow._get_recaptcha_token = AsyncMock(side_effect=RuntimeError('Paired tab unavailable'))
        flow._handle_retryable_generation_error = AsyncMock()
        flow._notify_browser_captcha_request_finished = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, 'Paired tab unavailable'):
            await flow.generate_image('marker', 'project', 'prompt', 'BELUGA', 'IMAGE_ASPECT_RATIO_SQUARE', token_id=7)
        flow._get_recaptcha_token.assert_awaited_once()
        flow._handle_retryable_generation_error.assert_not_awaited()

    async def test_browser_session_does_not_depend_on_an_old_exported_cookie_snapshot(self):
        token = Token(id=7, st='marker', email='a@example.com', browser_bridge_hash='hash')
        flow = FlowClient(None, SimpleNamespace(get_token=AsyncMock(return_value=token)))
        frames = json.dumps([['wrb.fr', 'nzlxg', json.dumps([42])]])
        with patch.object(browser_bridge, 'call', AsyncMock(return_value={'text': frames})):
            session = await flow.st_to_at('marker', google_cookies='expired-snapshot', token_id=7)
            self.assertEqual(session['credits'], 42)
            self.assertEqual(await flow._frontend_cookie(token_id=7), '')

    async def test_unrecognized_credit_response_never_becomes_a_false_zero(self):
        flow = FlowClient(None)
        flow._current_rpc = AsyncMock(return_value=[])
        with self.assertRaisesRegex(RuntimeError, 'balance is unknown'):
            await flow.get_credits('marker')

    async def test_connector_archive_includes_background_and_fixed_page_operations(self):
        import io
        import zipfile
        from src.main import connector_download
        response = await connector_download()
        with zipfile.ZipFile(io.BytesIO(response.body)) as bundle:
            names = bundle.namelist()
        self.assertIn('Flow-Account-Connector/background.js', names)
        self.assertIn('Flow-Account-Connector/page-bridge.js', names)
        self.assertIn('Flow-Account-Connector/page-captcha.js', names)


if __name__ == '__main__':
    unittest.main()


class BrowserBridgeSocketTests(unittest.TestCase):
    def test_socket_requires_extension_origin_and_matching_account_capability(self):
        secret = 'a' * 64
        token = Token(id=77, st='marker', email='a@example.com', browser_bridge_hash=hashlib.sha256(secret.encode()).hexdigest())
        db = SimpleNamespace(get_token=AsyncMock(return_value=token))
        manager = SimpleNamespace(refresh_credits=AsyncMock(return_value=42))
        app = FastAPI(); app.include_router(admin.router)
        with patch.object(admin, 'db', db), patch.object(admin, 'token_manager', manager):
            with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 1234)) as client:
                with client.websocket_connect('ws://127.0.0.1/api/browser-session/ws', headers={'origin': 'https://attacker.example'}) as ws:
                    with self.assertRaises(WebSocketDisconnect): ws.receive_json()
                with client.websocket_connect('ws://127.0.0.1/api/browser-session/ws', headers={'origin': 'chrome-extension://' + 'b' * 32}) as ws:
                    ws.send_json({'account_id': 77, 'secret': 'c' * 64})
                    with self.assertRaises(WebSocketDisconnect): ws.receive_json()
                self.assertFalse(browser_bridge.is_online(77))
                with client.websocket_connect('ws://127.0.0.1/api/browser-session/ws', headers={'origin': 'chrome-extension://' + 'b' * 32}) as ws:
                    ws.send_json({'account_id': 77, 'secret': secret})
                    self.assertEqual(ws.receive_json(), {'type': 'ready'})
                    self.assertTrue(browser_bridge.is_online(77))
            self.assertFalse(browser_bridge.is_online(77))
