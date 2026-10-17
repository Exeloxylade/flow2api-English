import asyncio,json,os,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
import httpx
from fastapi import FastAPI
from src.api import admin
from src.services.dashboard_login import DashboardLogin,DashboardSetupError
from start_local import ensure_configuration
EMAIL='owner@example.com'
RESULT={'success':True,'account':{'id':1,'email':EMAIL,'enabled':True}}

class DashboardJobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        environment=patch.dict(os.environ,{});environment.start();self.addCleanup(environment.stop)
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.service=DashboardLogin(self.root)
        self.service._browser=AsyncMock(return_value='test-browser')
        self.service._capture=AsyncMock(return_value=(EMAIL,'private-cookies'))
        self.register=AsyncMock(return_value=RESULT)
        p=patch('src.services.dashboard_login.sys.platform','win32');p.start();self.addCleanup(p.stop)
        self.addAsyncCleanup(self.service.close)

    async def test_add_registers_and_records_profile_without_credentials(self):
        started=await self.service.start(self.register);self.assertTrue(started['busy']);await self.service.task
        self.assertEqual(self.service.status()['phase'],'ready');self.assertFalse(self.service.status()['busy'])
        self.register.assert_awaited_once_with(EMAIL,'private-cookies',None)
        saved=(self.root/'profiles.json').read_text();self.assertIn(EMAIL,saved)
        self.assertNotIn('private-cookies',saved+json.dumps(self.service.status()))

    async def test_reconnect_reuses_profile_and_expected_identity(self):
        await self.service.start(self.register);await self.service.task
        first=self.service._capture.await_args.args[1]
        await self.service.start(self.register,email=EMAIL,account_id=1);await self.service.task
        self.assertEqual(self.service._capture.await_args.args[1],first)
        self.assertEqual(self.service._capture.await_args.args[2],EMAIL)
        self.assertEqual(self.register.await_args.args[2],1)

    async def test_duplicate_email_replaces_profile_and_removal_clears_mapping(self):
        await self.service.start(self.register);await self.service.task;first=self.service._capture.await_args.args[1]
        await self.service.start(self.register);await self.service.task
        self.assertFalse(first.exists());self.assertEqual(len(json.loads((self.root/'profiles.json').read_text())),1)
        self.service.forget(EMAIL);self.assertEqual(json.loads((self.root/'profiles.json').read_text()),{})

    async def test_multiple_accounts_keep_separate_profiles(self):
        self.service._capture.side_effect=[(EMAIL,'first-cookies'),('second@example.com','second-cookies')]
        await self.service.start(self.register);await self.service.task
        await self.service.start(self.register);await self.service.task
        profiles=json.loads((self.root/'profiles.json').read_text())
        self.assertEqual(len(profiles),2);self.assertNotEqual(profiles[EMAIL],profiles['second@example.com'])
        second=self.root/profiles['second@example.com']
        self.service.forget(EMAIL);self.assertTrue(second.is_dir())

    async def test_cancel_discards_new_profile_and_blocks_duplicate_or_stale_actions(self):
        waiting=asyncio.Event()
        async def capture(*args):waiting.set();await asyncio.Future()
        self.service._capture.side_effect=capture
        started=await self.service.start(self.register);await waiting.wait()
        with self.assertRaises(DashboardSetupError):await self.service.start(self.register)
        with self.assertRaises(DashboardSetupError):await self.service.cancel('stale-job')
        await self.service.cancel(started['job_id'])
        self.assertEqual(self.service.status()['phase'],'cancelled');self.register.assert_not_awaited()
        self.assertEqual(list(self.root.iterdir()),[])

    async def test_errors_do_not_expose_credentials(self):
        self.register.side_effect=RuntimeError('private-cookies')
        await self.service.start(self.register);await self.service.task
        self.assertEqual(self.service.status()['phase'],'error')
        self.assertNotIn('private-cookies',json.dumps(self.service.status()));self.assertEqual(list(self.root.iterdir()),[])

    async def test_saving_finishes_before_shutdown_or_cancel(self):
        waiting,finish=asyncio.Event(),asyncio.Event()
        async def register(*args):waiting.set();await finish.wait();return RESULT
        started=await self.service.start(register);await waiting.wait()
        with self.assertRaises(DashboardSetupError):await self.service.cancel(started['job_id'])
        finish.set();await self.service.task;self.assertEqual(self.service.status()['phase'],'ready')

    async def test_profile_traversal_rejected_before_browser(self):
        (self.root/'profiles.json').write_text(json.dumps({EMAIL:'../../outside'}))
        with self.assertRaises(DashboardSetupError):await self.service.start(self.register)
        self.service._browser.assert_not_awaited()

class DashboardApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service=types.SimpleNamespace(status=lambda:{'phase':'idle','busy':False},start=AsyncMock(return_value={'phase':'preparing'}),cancel=AsyncMock())
        self.db=types.SimpleNamespace(update_captcha_config=AsyncMock(),update_token_refresh_config=AsyncMock(),reload_config_to_memory=AsyncMock())
        self.manager=types.SimpleNamespace(get_token=AsyncMock(return_value=types.SimpleNamespace(email=EMAIL,login_account=EMAIL)))
        for name,value in [('dashboard_login',self.service),('db',self.db),('token_manager',self.manager),('browser_registration_lock',asyncio.Lock()),('local_dashboard_ticket','t'*48),('local_dashboard_ticket_deadline',time.monotonic()+60)]:
            p=patch.object(admin,name,value);p.start();self.addCleanup(p.stop)
        self.auth='dashboard-test-admin';admin.active_admin_tokens.add(self.auth);self.addCleanup(admin.active_admin_tokens.discard,self.auth)
        app=FastAPI();app.include_router(admin.router)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1234)),base_url='http://127.0.0.1:8000');self.addAsyncCleanup(self.client.aclose)
        self.headers={'Authorization':'Bearer '+self.auth}

    async def test_connect_applies_browser_and_refresh_settings(self):
        r=await self.client.post('/api/browser-login/start',headers=self.headers,json={'expected_account_id':1})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.service.start.await_args.kwargs,{'email':EMAIL,'account_id':1})
        register=self.service.start.await_args.args[0]
        with patch.object(admin,'register_browser_session',AsyncMock(return_value=RESULT)):await register(EMAIL,'private-cookies',1)
        self.db.update_captcha_config.assert_not_awaited()
        self.db.update_token_refresh_config.assert_awaited_once_with(enabled=True);self.db.reload_config_to_memory.assert_awaited_once()

    async def test_admin_and_local_same_origin_required(self):
        r=await self.client.post('/api/browser-login/start',json={});self.assertEqual(r.status_code,401)
        for extra in [{'Origin':'https://external.example'},{'Host':'remote.example'}]:
            r=await self.client.post('/api/browser-login/start',headers={**self.headers,**extra},json={});self.assertEqual(r.status_code,403)
        self.service.start.assert_not_awaited()

    async def test_deleted_reconnect_target_does_not_open_browser(self):
        self.manager.get_token.return_value=None
        r=await self.client.post('/api/browser-login/start',headers=self.headers,json={'expected_account_id':99})
        self.assertEqual(r.status_code,404);self.service.start.assert_not_awaited()

    async def test_launch_ticket_creates_httponly_cookie_and_is_one_use(self):
        r=await self.client.post('/api/local-dashboard',json={'ticket':'t'*48});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json(),{'success':True});self.assertIn('httponly',r.headers['set-cookie'].lower());self.assertIn('samesite=strict',r.headers['set-cookie'].lower())
        r=await self.client.post('/api/local-dashboard',json={'ticket':'t'*48});self.assertEqual(r.status_code,401)

    async def test_expired_or_cross_origin_launch_ticket_rejected(self):
        with patch.object(admin,'local_dashboard_ticket_deadline',0):
            r=await self.client.post('/api/local-dashboard',json={'ticket':'t'*48});self.assertEqual(r.status_code,401)
        r=await self.client.post('/api/local-dashboard',headers={'Origin':'https://external.example'},json={'ticket':'t'*48});self.assertEqual(r.status_code,403)

class LocalLauncherTests(unittest.TestCase):
    def test_bootstrap_updates_changed_requirements_once(self):
        import bootstrap_local
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'requirements.txt').write_text('example==1\n')
            with patch.object(bootstrap_local,'__file__',str(root/'bootstrap_local.py')),patch.object(bootstrap_local.subprocess,'run') as install,patch('start_local.main') as start:
                bootstrap_local.main()
                self.assertEqual((root/'.runtime/requirements.sha256').read_text(),hashlib.sha256((root/'requirements.txt').read_bytes()).hexdigest())
                bootstrap_local.main()
                install.assert_called_once();self.assertEqual(start.call_count,2)

    def test_configuration_is_private_and_existing_settings_preserved(self):
        import tomllib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'config').mkdir()
            (root/'config/setting_example.toml').write_text('[global]\napi_key="example"\nadmin_username="admin"\nadmin_password="admin"\n[server]\nhost="0.0.0.0"\n[captcha]\ncaptcha_method="browser"\n')
            ensure_configuration(root);file=root/'config/setting.toml';original=file.read_text();config=tomllib.loads(original)
            self.assertEqual(config['server']['host'],'127.0.0.1');self.assertEqual(config['captcha']['captcha_method'],'personal')
            self.assertNotEqual(config['global']['admin_password'],'admin');self.assertNotEqual(config['global']['api_key'],'example')
            ensure_configuration(root);self.assertEqual(file.read_text(),original)

if __name__=='__main__':unittest.main()
