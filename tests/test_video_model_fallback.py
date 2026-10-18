"""No browser or Google requests: contracts for explicit video model rejections."""
import types
import unittest
from unittest.mock import AsyncMock, Mock
from src.services.flow_current import CurrentFlowClientMixin


class VideoFallbackTests(unittest.IsolatedAsyncioTestCase):
    def client(self, errors, retries=1):
        client = CurrentFlowClientMixin()
        client._frontend_cookie = AsyncMock(return_value="")
        client._paired_browser_account = AsyncMock(return_value=object())
        client._get_runtime_config = lambda: types.SimpleNamespace(flow_max_retries=retries)
        client._get_recaptcha_token = AsyncMock(side_effect=[("fresh-one", "tab-one"), ("fresh-two", "tab-two")])
        client._build_flow_frontend_project_page_url = lambda p: "https://flow.google.com/project/" + p
        client._build_frontend_video_generation_argument = Mock(return_value=("eb1hJf", ["argument"]))
        client._get_video_submit_timeout = lambda: 90
        client._current_rpc = AsyncMock(side_effect=errors)
        client._normalize_frontend_video_submission = Mock(return_value={"ok": True})
        client._notify_browser_captcha_request_finished = AsyncMock()
        return client

    async def generate(self, client, model="veo_3_1_i2v_s_fast_6s_relaxed"):
        return await client._current_generate_video(project_id="project", prompt="scene", model_key=model,
            aspect_ratio="VIDEO_ASPECT_RATIO_LANDSCAPE", mode="start", token_id=7,
            token_video_concurrency=1, google_cookies=None, start_media_id="first-frame")

    async def test_missing_alias_uses_standard_same_duration_and_frame_once(self):
        c = self.client([RuntimeError("Flow frontend RPC rejected: rpc=eb1hJf, code=[5]"), {"result": True}])
        self.assertEqual(await self.generate(c), {"ok": True})
        first, second = [call.kwargs for call in c._build_frontend_video_generation_argument.call_args_list]
        self.assertEqual(first["model_key"], "veo_3_1_i2v_s_fast_6s_relaxed")
        self.assertEqual(second["model_key"], "veo_3_1_i2v_s_fast_6s")
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertNotEqual(first["recaptcha_token"], second["recaptcha_token"])
        for key in ("project_id", "prompt", "aspect_ratio", "mode", "start_media_id", "end_media_id", "reference_media_ids", "resolution"):
            self.assertEqual(first[key], second[key])
        self.assertEqual(c._normalize_frontend_video_submission.call_args.kwargs["model_key"], second["model_key"])
        self.assertEqual(c._notify_browser_captcha_request_finished.await_count, 2)
        for call in c._current_rpc.call_args_list:
            self.assertEqual(call.kwargs["token_id"], 7)

    async def test_failed_standard_key_does_not_loop(self):
        c = self.client([RuntimeError("code=[5]"), RuntimeError("code=[5]")], retries=5)
        with self.assertRaisesRegex(RuntimeError, "code"):
            await self.generate(c)
        self.assertEqual(c._current_rpc.await_count, 2)
        self.assertEqual(c._notify_browser_captcha_request_finished.await_count, 2)

    async def test_no_replay_on_uncertain_or_account_rejections(self):
        for message in ("PUBLIC_ERROR_UNUSUAL_ACTIVITY", "MODEL_ACCESS_DENIED", "request timeout", "code=[50]", "captcha/request_failed"):
            with self.subTest(message=message):
                c = self.client([RuntimeError(message)], retries=5)
                with self.assertRaises(RuntimeError):
                    await self.generate(c)
                self.assertEqual(c._current_rpc.await_count, 1)
                self.assertEqual(c._notify_browser_captcha_request_finished.await_count, 1)

    async def test_standard_key_is_not_changed(self):
        c = self.client([RuntimeError("code=[5]")])
        with self.assertRaises(RuntimeError):
            await self.generate(c, "veo_3_1_i2v_s_fast_6s")
        self.assertEqual(c._current_rpc.await_count, 1)

    async def test_success_has_one_submission(self):
        c = self.client([{}])
        await self.generate(c)
        self.assertEqual(c._current_rpc.await_count, 1)
