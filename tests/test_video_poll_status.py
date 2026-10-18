"""Video polling contracts. No browser, external requests, or real generation."""
import json
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
from src.services.flow_frontend import FlowFrontendMixin
from src.services.flow_current import CurrentFlowClientMixin
from src.services.generation_handler import GenerationHandler

OP = "11111111-1111-1111-1111-111111111111"
PROJECT = "22222222-2222-2222-2222-222222222222"
MEDIA = "33333333-3333-3333-3333-333333333333"
OTHER = "44444444-4444-4444-4444-444444444444"
URL = f"https://flow-content.google/video/{MEDIA}?token=never-log-this"

def operation():
    return {"name": OP, "operation": {"name": OP}, "projectId": PROJECT, "mediaName": MEDIA, "status": "MEDIA_GENERATION_STATUS_ACTIVE"}

def record(*extra, operation_id=OP, project=PROJECT):
    return [operation_id, project, MEDIA, *extra]

class StatusAdapterTests(unittest.TestCase):
    def normalize(self, payload):
        return FlowFrontendMixin._normalize_frontend_video_status(payload, [operation()])["operations"][0]

    def test_missing_or_foreign_results_do_not_reuse_active_or_another_video(self):
        for payload in ([], [None], record(URL, operation_id=OTHER), record(URL, project=OTHER)):
            with self.subTest(payload=payload):
                result = self.normalize(payload)
                self.assertEqual(result["name"], OP)
                self.assertEqual(result["status"], "MEDIA_GENERATION_STATUS_UNKNOWN")
                self.assertNotIn(URL, json.dumps(result))

    def test_numeric_unrecognized_fields_are_not_guessed_as_active(self):
        result = self.normalize(record(None, [7, 19]))
        self.assertEqual(result["status"], "MEDIA_GENERATION_STATUS_UNKNOWN")

    def test_explicit_active_success_failed_and_cancelled_states(self):
        for name in ("ACTIVE", "SUCCESSFUL", "FAILED", "CANCELLED"):
            with self.subTest(name=name):
                state = "MEDIA_GENERATION_STATUS_" + name
                result = self.normalize(record({"status": state}))
                expected = "MEDIA_GENERATION_STATUS_FAILED" if name == "CANCELLED" else state
                self.assertEqual(result["status"], expected)

    def test_nested_failure_is_not_overridden_by_a_url_in_the_same_record(self):
        result = self.normalize(record(URL, {"error": {"code": "PUBLIC_ERROR_MODEL_ACCESS_DENIED"}}))
        self.assertEqual(result["status"], "MEDIA_GENERATION_STATUS_FAILED")
        self.assertEqual(result["operation"]["error"]["code"], "PUBLIC_ERROR_MODEL_ACCESS_DENIED")
        self.assertNotEqual(result["progress"], 100)

    def test_matching_operation_with_omitted_project_can_complete(self):
        result = self.normalize(record(URL, project=None))
        self.assertEqual(result["status"], "MEDIA_GENERATION_STATUS_SUCCESSFUL")

    def test_matching_signed_video_result_is_success(self):
        result = self.normalize(record(URL))
        self.assertEqual(result["status"], "MEDIA_GENERATION_STATUS_SUCCESSFUL")
        self.assertEqual(result["operation"]["metadata"]["video"]["fifeUrl"], URL)

class SubmissionValidationTests(unittest.TestCase):
    def normalize(self, payload):
        return FlowFrontendMixin._normalize_frontend_video_submission(payload, project_id=PROJECT,
            model_key="abra_r2v_4s", aspect_ratio="VIDEO_ASPECT_RATIO_PORTRAIT", input_media_ids=[MEDIA])

    def test_upload_reference_records_are_not_video_jobs(self):
        with self.assertRaisesRegex(RuntimeError, "no generation operations"):
            self.normalize([record()])

    def test_returned_generation_keeps_only_output_record(self):
        output = [OTHER, PROJECT, "55555555-5555-5555-5555-555555555555"]
        result = self.normalize([record(), output])
        self.assertEqual([op["name"] for op in result["operations"]], [OTHER])

    def test_nested_submission_error_is_not_discarded_as_active(self):
        with self.assertRaisesRegex(RuntimeError, "PUBLIC_ERROR_MODEL_ACCESS_DENIED"):
            self.normalize([record(), {"error": "PUBLIC_ERROR_MODEL_ACCESS_DENIED"}])

class Client(CurrentFlowClientMixin, FlowFrontendMixin):
    pass

class StatusLookupTests(unittest.IsolatedAsyncioTestCase):
    def client(self, payload, media=None):
        client = Client()
        client._current_rpc = AsyncMock(return_value=payload)
        client._get_video_poll_timeout = lambda: 30
        client.get_media = AsyncMock(return_value=media or {"video": {"fifeUrl": ""}})
        return client

    async def test_media_lookup_can_recover_an_unrecognized_status(self):
        client = self.client([], {"video": {"fifeUrl": URL}})
        result = await client.check_video_status("", [operation()], token_id=9)
        self.assertEqual(result["operations"][0]["status"], "MEDIA_GENERATION_STATUS_SUCCESSFUL")
        self.assertEqual(result["operations"][0]["statusSource"], "media_lookup")
        self.assertEqual(client.get_media.call_args.kwargs["operation_id"], OP)

    async def test_terminal_failure_is_not_replaced_by_media_fallback(self):
        client = self.client(record({"error": "PUBLIC_ERROR_UNSAFE_GENERATION"}), {"video": {"fifeUrl": URL}})
        result = await client.check_video_status("", [operation()])
        self.assertEqual(result["operations"][0]["status"], "MEDIA_GENERATION_STATUS_FAILED")
        client.get_media.assert_not_awaited()

    async def test_result_lookup_public_rejection_is_terminal_and_safe(self):
        client = self.client([])
        client.get_media.side_effect = RuntimeError("rpc rejected: PUBLIC_ERROR_MODEL_ACCESS_DENIED secret-cookie")
        result = await client.check_video_status("", [operation()])
        self.assertEqual(result["operations"][0]["status"], "MEDIA_GENERATION_STATUS_FAILED")
        self.assertNotIn("secret-cookie", json.dumps(result))

    async def test_unready_media_lookup_keeps_status_unknown_without_resubmitting(self):
        client = self.client([])
        client.get_media.side_effect = RuntimeError("rpc=as29s code=[5]")
        result = await client.check_video_status("", [operation()])
        self.assertEqual(result["operations"][0]["status"], "MEDIA_GENERATION_STATUS_UNKNOWN")
        self.assertEqual(client._current_rpc.await_count, 1)

class PollLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_unrecognized_status_reports_diagnostics_then_times_out_without_new_submission(self):
        handler = GenerationHandler.__new__(GenerationHandler)
        op = {**operation(), "status": "MEDIA_GENERATION_STATUS_UNKNOWN", "statusSource": "unrecognized_response"}
        handler.flow_client = types.SimpleNamespace(check_video_status=AsyncMock(return_value={"operations": [op], "response_record_count": 0, "matched_record_count": 0}))
        handler._update_request_log_progress = AsyncMock()
        handler._fail_video_task = AsyncMock()
        handler._mark_generation_failed = Mock()
        handler._create_error_response = lambda message, status_code: {"error": message, "code": status_code}
        token = types.SimpleNamespace(id=9, at="fake", user_paygate_tier="PAYGATE_TIER_ONE")
        with patch("src.services.generation_handler.config", types.SimpleNamespace(poll_interval=.1, video_timeout=.2)), patch("src.services.generation_handler.asyncio.sleep", AsyncMock()):
            result = [item async for item in handler._poll_video_result(token, PROJECT, [operation()], False, response_state={}, request_log_state={"id": 1})]
        self.assertEqual(result[-1]["code"], 504)
        self.assertIn("could not be recognized", result[-1]["error"])
        self.assertIn("before retrying", result[-1]["error"])
        report = handler._update_request_log_progress.call_args.kwargs
        self.assertEqual(report["status_text"], "video_status_unknown")
        self.assertEqual(report["progress"], 45)
        self.assertEqual(report["response_extra"]["matched_record_count"], 0)
        self.assertEqual(handler.flow_client.check_video_status.await_count, 2)
        handler._fail_video_task.assert_awaited_once()

    async def test_processing_duration_is_elapsed_time_not_zero(self):
        handler = GenerationHandler.__new__(GenerationHandler)
        handler.db = types.SimpleNamespace(update_request_log=AsyncMock())
        state = {"id": 1, "started_at": 10}
        with patch("src.services.generation_handler.time.time", return_value=70):
            await handler._update_request_log_progress(state, token_id=9, status_text="video_status_unknown", progress=45)
        self.assertEqual(handler.db.update_request_log.call_args.kwargs["duration"], 60)


# Schema fixture transcribed from the primary wire investigation (not user data):
# https://github.com/ffroliva/gflow-cli/blob/develop/docs/superpowers/spikes/2026-09-05-migrated-host-wire-protocol.md
SIGNED_VIDEO = "https://flow-content.google/opaque-result?Expires=123&Signature=fixture"
POSTER = "https://flow-content.google/opaque-poster?Expires=123&Signature=fixture"

def migrated_record(state=3, video=SIGNED_VIDEO, poster=POSTER):
    details = [None] * 14
    details[8] = [state]
    details[10] = poster
    info = [None] * 17
    info[8] = video
    info[12] = "abra_t2v_8s"
    return [OP, PROJECT, MEDIA, "CAE", None, details, None, [info, [None, None, [8]], [OP]]]

class MigratedVideoWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_completion_and_opaque_signed_url_return_video_not_poster(self):
        client = Client()
        client._get_video_poll_timeout = lambda: 30
        client._current_rpc = AsyncMock(side_effect=[migrated_record(video=None), migrated_record()])
        result = await client.check_video_status("", [operation()], token_id=9)
        op = result["operations"][0]
        self.assertEqual(op["status"], "MEDIA_GENERATION_STATUS_SUCCESSFUL")
        self.assertEqual(op["operation"]["metadata"]["video"]["fifeUrl"], SIGNED_VIDEO)
        self.assertNotIn(POSTER, json.dumps(result))
        self.assertEqual(client._current_rpc.await_args.kwargs["rpc_id"], "as29s")

    async def test_completed_state_waits_for_media_url_instead_of_returning_poster(self):
        client = Client()
        client._get_video_poll_timeout = lambda: 30
        client._current_rpc = AsyncMock(return_value=migrated_record(video=None))
        result = await client.check_video_status("", [operation()])
        op = result["operations"][0]
        self.assertEqual(op["status"], "MEDIA_GENERATION_STATUS_PENDING")
        self.assertNotIn(POSTER, json.dumps(result))

    async def test_wire_enum_is_read_only_at_documented_position(self):
        for number, expected in [(2, "ACTIVE"), (6, "QUEUED"), (3, "PENDING"), (99, "UNKNOWN")]:
            result = FlowFrontendMixin._normalize_frontend_video_status(migrated_record(number, video=None), [operation()])
            self.assertEqual(result["operations"][0]["status"], "MEDIA_GENERATION_STATUS_"+expected)
        row = migrated_record(video=None)
        row[5][8] = [7, 19]
        self.assertEqual(FlowFrontendMixin._frontend_video_record_result(row)[1], "")

    async def test_media_info_urls_require_https_and_expected_media_host(self):
        for url in ["http://flow-content.google/file", "https://attacker.example/file", "https://flow-content.google.attacker.example/file", "https://user:secret@flow-content.google/file"]:
            self.assertEqual(FlowFrontendMixin._frontend_video_record_result(migrated_record(video=url))[0], "")
        row=migrated_record()
        row[7][0][8]=None
        self.assertEqual(FlowFrontendMixin._find_flow_content_url(row, "video"), "")
