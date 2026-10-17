"""Exercise the shipped login helper without accessing a Google account or launching a browser."""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE = (Path(__file__).parent / '../src/services/browser_login.py').read_text(encoding='utf-8')

class LoginTests(unittest.TestCase):
    def run_helper(self, email='owner@example.com', expected='', host='flow.google.com', cookie_host='.google.com', closed=False):
        with tempfile.TemporaryDirectory() as folder:
            state = {'closed': False, 'reads': 0}
            class Process:
                pid = 123
                def poll(self): return 0 if state['closed'] else None
                def wait(self, timeout=None): state['closed'] = True
                def kill(self): state['closed'] = True
            def launch(args, **kwargs):
                self.assertIn('--remote-debugging-address=127.0.0.1', args)
                self.assertIn('--user-data-dir=' + folder, args)
                Path(folder, 'DevToolsActivePort').write_text('45678\n/devtools/browser/test')
                return Process()
            class Page:
                url = 'https://' + host + '/projects'
                async def evaluate(self, js): return {'host': host, 'email': email}
                def is_closed(self): return False
            class Context:
                @property
                def pages(self):
                    state['reads'] += 1
                    return [] if closed or state['reads'] > 4 else [Page()]
                async def cookies(self): return [
                    {'name': 'OSID', 'value': 'fake', 'domain': cookie_host},
                    {'name': 'SID', 'value': 'fake', 'domain': cookie_host},
                    {'name': 'other', 'value': 'private', 'domain': '.example.org'},
                    {'name': 'partitioned', 'value': 'private', 'domain': '.google.com', 'partitionKey': 'https://example.org'}]
            class Session:
                async def send(self, command): state['closed'] = True
            class Browser:
                contexts = [Context()]
                async def new_browser_cdp_session(self): return Session()
            class Chromium:
                async def connect_over_cdp(self, url):
                    self_url = url
                    if self_url != 'http://127.0.0.1:45678': raise AssertionError(url)
                    return Browser()
            class Playwright:
                chromium = Chromium()
                async def __aenter__(self): return self
                async def __aexit__(self, *args): pass
            module = types.ModuleType('playwright.async_api')
            module.async_playwright = Playwright
            output = io.StringIO()
            async def instant_sleep(_seconds): pass
            with patch.dict(sys.modules, {'playwright': types.ModuleType('playwright'), 'playwright.async_api': module}), patch.dict(os.environ, {'BANG_LOGIN_PROFILE': folder, 'BROWSER_EXECUTABLE_PATH': 'test-chrome', 'BANG_LOGIN_EMAIL': expected}), patch.object(subprocess, 'Popen', launch), patch.object(asyncio, 'sleep', instant_sleep), contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as result:
                    exec(compile(SOURCE, 'bang-story-login.py', 'exec'), {'__name__': '__main__'})
            self.assertTrue(state['closed'])
            return result.exception.code, output.getvalue()

    def test_success_exports_only_unpartitioned_google_cookies(self):
        code, output = self.run_helper()
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data['email'], 'owner@example.com')
        self.assertEqual([c['name'] for c in data['cookies']], ['OSID', 'SID'])

    def test_reconnect_rejects_another_identity(self):
        code, output = self.run_helper(expected='another@example.com')
        self.assertEqual(code, 3)
        self.assertEqual(output, '')

    def test_closed_browser_is_cancelled(self):
        self.assertEqual(self.run_helper(closed=True), (2, ''))

    def test_non_flow_page_cannot_export_credentials(self):
        self.assertEqual(self.run_helper(host='example.org'), (2, ''))

    def test_no_google_cookies_cannot_export_credentials(self):
        self.assertEqual(self.run_helper(cookie_host='.evilgoogle.com'), (2, ''))

    def test_invalid_identity_cannot_export_credentials(self):
        self.assertEqual(self.run_helper(email='not-an-email'), (2, ''))

if __name__ == '__main__':
    unittest.main()
