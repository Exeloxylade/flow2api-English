"""Full local video pipeline against synthetic Google RPC responses; no live generation."""
import base64
import json
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
from src.core.models import Token
from src.services.flow_client import FlowClient
from src.services.browser_bridge import browser_bridge
from src.services.generation_handler import GenerationHandler, MODEL_CONFIG

PROJECT="22222222-2222-2222-2222-222222222222"
INPUT="33333333-3333-3333-3333-333333333333"
OP="11111111-1111-1111-1111-111111111111"
ASSET="55555555-5555-5555-5555-555555555555"
VIDEO="https://flow-content.google/opaque-generated-clip?Expires=123&Signature=fixture"
PNG=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6fN8AAAAASUVORK5CYII=")

class VideoPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_reference_upload_submission_poll_media_lookup_and_video_delivery(self):
        for model in ("omni-1.1-flash-4s-portrait", "veo-3.1-fast-i2v-6s-portrait", "veo-3.1-fast-i2v-6s-landscape"):
            with self.subTest(model=model):
                token=Token(id=7,st="marker",at="marker",email="owner@example.com",browser_bridge_hash="hash",user_paygate_tier="PAYGATE_TIER_ONE")
                db=types.SimpleNamespace(get_token=AsyncMock(return_value=token),create_task=AsyncMock(),update_task=AsyncMock())
                flow=FlowClient(None,db)
                flow._get_recaptcha_token=AsyncMock(return_value=("synthetic-captcha",None))
                flow._notify_browser_captcha_request_finished=AsyncMock()
                calls=[];lookups=0
                async def fake_bridge(account,email,operation,**job):
                    nonlocal lookups
                    self.assertEqual((account,email,operation),(7,token.email,"rpc"))
                    calls.append(job)
                    rpc=job["rpc_id"]
                    if rpc=="maseQ":
                        self.assertEqual(base64.b64decode(job["argument"][1]),PNG)
                        payload=[[INPUT,PROJECT,ASSET,f"https://flow-content.google/image/{INPUT}"]]
                    elif rpc in {"MZZa6b","eb1hJf"}:
                        # Mixed input and output records must retain the output job only.
                        payload=[[INPUT,PROJECT,ASSET],[OP,PROJECT,ASSET]]
                    elif rpc=="jwpduf":
                        self.assertEqual(job["argument"][2],[[OP]])
                        payload=[]
                    elif rpc=="as29s":
                        self.assertEqual(job["argument"],[OP])
                        self.assertEqual(job["source_path"],f"/project/{PROJECT}/edit/{ASSET}")
                        lookups+=1
                        details=[None]*14;details[8]=[3]
                        details[10]="https://flow-content.google/poster?Signature=fixture"
                        info=[None]*17;info[8]=VIDEO
                        payload=[] if lookups==1 else [OP,PROJECT,ASSET,"CAE",None,details,None,[info,[None,None,[8]],[OP]]]
                    else:
                        self.fail("Unexpected RPC in video pipeline: "+rpc)
                    return {"text":json.dumps([["wrb.fr",rpc,json.dumps(payload)]])}
                handler=GenerationHandler.__new__(GenerationHandler)
                handler.flow_client=flow;handler.db=db;handler.proxy_manager=None
                handler.token_manager=types.SimpleNamespace(record_usage=AsyncMock(),record_success=AsyncMock())
                handler.load_balancer=types.SimpleNamespace(clear_quota_cooldown=Mock())
                handler._update_request_log_progress=AsyncMock()
                state={};result=handler._create_generation_result()
                cfg=types.SimpleNamespace(poll_interval=.1,video_timeout=3,cache_enabled=False)
                with patch.object(browser_bridge,"call",AsyncMock(side_effect=fake_bridge)),patch("src.services.generation_handler.config",cfg),patch("src.services.generation_handler.asyncio.sleep",AsyncMock()):
                    output=[chunk async for chunk in handler._handle_video_generation(token,PROJECT,MODEL_CONFIG[model],"A paper flag moves in the wind.",[PNG],False,generation_result=result,response_state=state)]
                self.assertIn(VIDEO,output[-1])
                self.assertEqual(state["url"],VIDEO)
                db.create_task.assert_awaited_once()
                self.assertEqual(db.create_task.call_args.args[0].task_id,OP)
                self.assertEqual(db.update_task.call_args.kwargs["status"],"completed")
                self.assertTrue(result["success"])
                self.assertEqual(len([c for c in calls if c["rpc_id"] in {"MZZa6b","eb1hJf"}]),1)
                if model.startswith("veo"):
                    submit=next(c for c in calls if c["rpc_id"]=="eb1hJf")
                    self.assertEqual(submit["argument"][0][0][4][1],INPUT)
                else:
                    submit=next(c for c in calls if c["rpc_id"]=="MZZa6b")
                    self.assertEqual(submit["argument"][0][0][1][0][1],INPUT)

    async def test_unresponsive_paired_tab_is_not_reported_as_generic_no_token(self):
        from src.services.load_balancer import LoadBalancer
        token=Token(id=7,st="marker",email="owner@example.com",browser_bridge_hash="hash",video_enabled=True,last_st_refresh_result="RuntimeError: The paired Flow tab did not respond in time. private-session-value")
        manager=types.SimpleNamespace(get_active_tokens=AsyncMock(return_value=[token]))
        balancer=LoadBalancer(manager)
        with patch.object(browser_bridge,"is_online",return_value=True):
            reason=await balancer.get_unavailable_reason(for_video_generation=True,model="omni-1.1-flash-4s-portrait")
        self.assertIn("account verification",reason)
        self.assertIn("browser/request_timeout",reason)
        self.assertNotIn("private-session-value",reason)
