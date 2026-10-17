import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.api import admin
from src.core.config import config
from src.core.database import Database
from src.core.models import CaptchaConfig, Token
from src.services.browser_bridge import browser_bridge
from src.services.captcha_routing import resolve_captcha_method
from src.services.flow_client import FlowClient


class CaptchaRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        scope = patch.dict(config.get_raw_config(), {"captcha": {"captcha_method": "personal"}})
        scope.start()
        self.addCleanup(scope.stop)
        self.account = Token(id=7, st="marker", email="owner@example.com", browser_bridge_hash="hash")
        self.flow = FlowClient(None, types.SimpleNamespace(get_token=AsyncMock(return_value=self.account)))

    async def test_upgrade_default_keeps_paired_tab_without_managed_browser(self):
        with patch.object(browser_bridge, "call", AsyncMock(return_value={"token": "paired-token"})) as bridge:
            self.assertEqual(await self.flow._get_recaptcha_token("project", token_id=7), ("paired-token", None))
        self.assertEqual(bridge.await_args.args[:3], (7, "owner@example.com", "captcha"))
        self.assertEqual(self.flow._get_captcha_request_context()["method"], "paired_browser")

    async def test_selected_upstream_personal_provider_is_not_skipped_for_paired_account(self):
        config.get_raw_config()["captcha"]["captcha_method_explicit"] = True
        service = types.SimpleNamespace(get_token_bundle=AsyncMock(return_value={
            "token": "upstream-token", "fingerprint": {"user_agent": "fixture-UA"}, "session_id": "fixture-session",
        }))
        module = types.ModuleType("src.services.browser_captcha_personal")
        module.BrowserCaptchaService = types.SimpleNamespace(get_instance=AsyncMock(return_value=service))
        with patch.dict(sys.modules, {module.__name__: module}), patch.object(browser_bridge, "call", AsyncMock()) as bridge:
            self.assertEqual(await self.flow._get_recaptcha_token("project", token_id=7), ("upstream-token", "personal:fixture-session"))
        bridge.assert_not_awaited()
        service.get_token_bundle.assert_awaited_once_with("project", "IMAGE_GENERATION", token_id=7)

    async def test_request_override_reaches_upstream_worker_and_preserves_account_routing(self):
        service = types.SimpleNamespace(get_token=AsyncMock(return_value="worker-token"))
        with patch("src.services.browser_captcha_extension.ExtensionCaptchaService.get_instance", AsyncMock(return_value=service)), patch.object(browser_bridge, "call", AsyncMock()) as bridge:
            result = await self.flow._get_recaptcha_token("project", token_id=7, method_override="extension")
        self.assertEqual(result, ("worker-token", None))
        bridge.assert_not_awaited()
        service.get_token.assert_awaited_once_with("project", "IMAGE_GENERATION", timeout=25, token_id=7)

    async def test_explicit_worker_choice_is_honored(self):
        config.get_raw_config()["captcha"].update(captcha_method="extension", captcha_method_explicit=True)
        service = types.SimpleNamespace(get_token=AsyncMock(return_value="worker-token"))
        with patch("src.services.browser_captcha_extension.ExtensionCaptchaService.get_instance", AsyncMock(return_value=service)), patch.object(browser_bridge, "call", AsyncMock()) as bridge:
            self.assertEqual(await self.flow._get_recaptcha_token("project", token_id=7), ("worker-token", None))
        bridge.assert_not_awaited()

    async def test_paired_mode_without_pairing_and_empty_tokens_fail_clearly(self):
        self.account.browser_bridge_hash = ""
        with self.assertRaisesRegex(RuntimeError, "requires an account connected"):
            await self.flow._get_recaptcha_token("project", token_id=7, method_override="paired_browser")
        self.account.browser_bridge_hash = "hash"
        with patch.object(browser_bridge, "call", AsyncMock(return_value={"token": ""})):
            with self.assertRaisesRegex(RuntimeError, "no CAPTCHA token"):
                await self.flow._get_recaptcha_token("project", token_id=7)

    def test_legacy_accounts_keep_their_configured_provider(self):
        for method in ["personal", "browser", "extension", "yescaptcha", "remote_browser"]:
            self.assertEqual(resolve_captcha_method(method, paired=False), method)
            self.assertEqual(resolve_captcha_method(method, paired=True, explicit=True), method)
        self.assertEqual(resolve_captcha_method("personal", paired=True), "paired_browser")


class CaptchaSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Database(str(Path(tmp.name) / "settings.db"))
        await self.db.init_db()
        scope = patch.dict(config.get_raw_config(), {"captcha": {"captcha_method": "personal"}})
        scope.start()
        self.addCleanup(scope.stop)
        scope = patch.object(admin, "db", self.db)
        scope.start()
        self.addCleanup(scope.stop)

    async def test_dashboard_selection_survives_reload_and_auto_keeps_legacy_fallback(self):
        with patch.object(admin, "_schedule_captcha_runtime_prepare", return_value=False):
            result = await admin.update_captcha_config({"captcha_method": "personal"}, token="fixture")
        self.assertTrue(result["success"])
        saved = await self.db.get_captcha_config()
        self.assertEqual(saved.captcha_method, "personal")
        self.assertTrue(saved.captcha_method_explicit)
        await self.db.reload_config_to_memory()
        self.assertTrue(config.captcha_method_explicit)
        self.assertEqual((await admin.get_captcha_config(token="fixture"))["captcha_method"], "personal")
        await admin.update_captcha_config({"captcha_method": "auto"}, token="fixture")
        saved = await self.db.get_captcha_config()
        self.assertFalse(saved.captcha_method_explicit)
        self.assertEqual(saved.captcha_method, "personal")
        shown = await admin.get_captcha_config(token="fixture")
        self.assertEqual(shown["captcha_method"], "auto")
        self.assertEqual(shown["auto_fallback_method"], "personal")

    async def test_invalid_method_does_not_modify_saved_choice(self):
        for invalid in ["unrecognized", [], 4]:
            result = await admin.update_captcha_config({"captcha_method": invalid}, token="fixture")
            self.assertFalse(result["success"])
        self.assertFalse((await self.db.get_captcha_config()).captcha_method_explicit)

    async def test_paired_score_test_does_not_start_managed_browser(self):
        await self.db.update_captcha_config(captcha_method="paired_browser", captcha_method_explicit=True)
        with patch.object(admin, "_schedule_captcha_runtime_prepare") as prepare:
            result = await admin.test_captcha_score(_token="fixture")
        self.assertFalse(result["success"])
        self.assertEqual(result["captcha_method"], "paired_browser")
        prepare.assert_not_called()

    async def test_old_database_migrates_without_changing_provider(self):
        await self.db.update_captcha_config(captcha_method="extension")
        async with self.db._connect(write=True) as connection:
            await connection.execute("ALTER TABLE captcha_config DROP COLUMN captcha_method_explicit")
            await connection.commit()
        await self.db.check_and_migrate_db()
        saved = await self.db.get_captcha_config()
        self.assertFalse(saved.captcha_method_explicit)
        self.assertEqual(saved.captcha_method, "extension")


if __name__ == "__main__":
    unittest.main()
