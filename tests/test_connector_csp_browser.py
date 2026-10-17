"""Browser regression for the real TrustedScriptURL failure (no Google account)."""
import json
import os
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright


class ConnectorCspBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        options = {"headless": True}
        if os.environ.get("FLOW_TEST_CHROMIUM_EXECUTABLE"):
            options["executable_path"] = os.environ["FLOW_TEST_CHROMIUM_EXECUTABLE"]
        cls.browser = cls.playwright.chromium.launch(**options)
        cls.source = (Path(__file__).parents[1] / "browser-extension/page-bridge.js").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def run_fixture(self, policy_allowed=True):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        script_requests = []
        policy = "flow-account-connector#recaptcha" if policy_allowed else "page-only-policy"
        csp = f"script-src 'nonce-fixture-nonce'; require-trusted-types-for 'script'; trusted-types {policy}"
        def route_request(route):
            url = route.request.url
            if url == "https://flow.google.com/projects":
                route.fulfill(status=200, headers={"Content-Security-Policy": csp}, content_type="text/html", body='''
                    <!doctype html><html><head><script nonce="fixture-nonce">
                    window.WIZ_global_data={oPEP7c:'owner@example.com'};
                    </script></head><body>Local browser fixture</body></html>''')
            elif url.startswith("https://www.google.com/recaptcha/enterprise.js?render="):
                script_requests.append(url)
                route.fulfill(status=200, content_type="application/javascript", body="""
                    window.grecaptcha={enterprise:{ready:callback=>callback(),execute:async()=> 'fixture-only-token'}};
                """)
            else:
                route.abort()
        page.route("**/*", route_request)
        page.goto("https://flow.google.com/projects")
        return page, script_requests

    def test_real_browser_requires_trusted_url_then_connector_loads_with_nonce(self):
        page, requests = self.run_fixture()
        rejected = page.evaluate("""() => {
            try {document.createElement('script').src='https://www.google.com/recaptcha/enterprise.js';return false;}
            catch(e) {return e instanceof TypeError;}
        }""")
        self.assertTrue(rejected, "Fixture must reproduce the browser's TrustedScriptURL enforcement")
        job = {"operation": "captcha", "action": "IMAGE_GENERATION", "email": "owner@example.com"}
        result = page.evaluate(f"async () => {{ {self.source}; return await runFlowOperation({json.dumps(job)}); }}")
        self.assertEqual(result, {"success": True, "result": {"token": "fixture-only-token"}})
        self.assertEqual(len(requests), 1)
        self.assertEqual(page.evaluate("document.querySelector('script[src]').nonce"), "fixture-nonce")
        self.assertIsNone(page.evaluate("window.trustedTypes.defaultPolicy"))

    def test_restrictive_page_policy_is_respected_without_loading_script(self):
        page, requests = self.run_fixture(policy_allowed=False)
        job = {"operation": "captcha", "action": "IMAGE_GENERATION", "email": "owner@example.com"}
        result = page.evaluate(f"async () => {{ {self.source}; return await runFlowOperation({json.dumps(job)}); }}")
        self.assertEqual(result, {"success": False, "error_code": "captcha_script_failed"})
        self.assertEqual(requests, [])
        self.assertIsNone(page.evaluate("window.trustedTypes.defaultPolicy"))


if __name__ == "__main__":
    unittest.main()
