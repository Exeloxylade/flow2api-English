import unittest
from unittest.mock import AsyncMock
from datetime import datetime, timedelta, timezone

from src.core.models import Token
from src.services.token_manager import TokenManager


class PositionalCreditsClient:
    def __init__(self):
        self.request_fingerprint = None

    def get_request_fingerprint(self):
        return self.request_fingerprint

    def _set_request_fingerprint(self, fingerprint):
        self.request_fingerprint = fingerprint

    async def get_credits(self, at, *, google_cookies=None, token_id=None):
        if at != "valid-at":
            raise AssertionError("credit lookup did not use the validated access token")
        if google_cookies != "account-cookie-jar" or token_id != 7:
            raise AssertionError("credit lookup lost its account cookie context")
        return {"credits": 42, "userPaygateTier": "PAYGATE_TIER_ONE"}


class CreditRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_credits_uses_supported_flow_client_signature(self):
        token = Token(
            id=7,
            st="session",
            at="valid-at",
            email="user@example.com",
            google_cookies="account-cookie-jar",
        )
        db = type("DatabaseStub", (), {})()
        db.get_token = AsyncMock(return_value=token)
        db.update_token = AsyncMock()
        flow_client = PositionalCreditsClient()
        manager = TokenManager(db, flow_client)
        manager.ensure_valid_token = AsyncMock(return_value=token)

        credits = await manager.refresh_credits(token.id)

        self.assertEqual(credits, 42)
        db.update_token.assert_awaited_once_with(
            token.id,
            credits=42,
            user_paygate_tier="PAYGATE_TIER_ONE",
            credits_updated_at=unittest.mock.ANY,
        )

    async def test_token_with_more_than_five_minutes_left_is_not_proactively_refreshed(self):
        token = Token(
            id=7,
            st="session",
            at="valid-at",
            at_expires=datetime.now(timezone.utc) + timedelta(minutes=54),
            email="user@example.com",
        )
        manager = TokenManager(None, None)

        self.assertFalse(manager.needs_at_refresh(token))

    async def test_token_with_less_than_five_minutes_left_needs_refresh(self):
        token = Token(
            id=7,
            st="session",
            at="valid-at",
            at_expires=datetime.now(timezone.utc) + timedelta(minutes=4),
            email="user@example.com",
        )
        manager = TokenManager(None, None)

        self.assertTrue(manager.needs_at_refresh(token))


if __name__ == "__main__":
    unittest.main()


class PairedCreditRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_accounts_verify_once_each_and_zero_is_a_valid_balance(self):
        from types import SimpleNamespace
        accounts={i:Token(id=i,st='marker',at='marker',email=f'account{i}@example.com',browser_bridge_hash='hash') for i in [7,8]}
        db=SimpleNamespace(get_token=AsyncMock(side_effect=lambda i: accounts[i]), update_token=AsyncMock())
        flow=SimpleNamespace(get_request_fingerprint=lambda:None,_set_request_fingerprint=lambda value:None,
            get_credits=AsyncMock(side_effect=[{'credits':12},{'credits':0}]))
        manager=TokenManager(db,flow);manager.ensure_valid_token=AsyncMock(side_effect=AssertionError('legacy verification used'))
        self.assertEqual(await manager.refresh_credits(7),12)
        self.assertEqual(await manager.refresh_credits(8),0)
        self.assertEqual([call.kwargs['token_id'] for call in flow.get_credits.await_args_list],[7,8])
        self.assertEqual(flow.get_credits.await_count,2)
        self.assertIsNotNone(db.update_token.await_args_list[-1].kwargs['credits_updated_at'])
        self.assertEqual(db.update_token.await_args_list[-1].kwargs['last_st_refresh_result'],'Browser session verified')
        manager.ensure_valid_token.assert_not_awaited()

    async def test_second_account_failure_preserves_its_pairing_and_first_account(self):
        from types import SimpleNamespace
        token=Token(id=8,st='marker',at='marker',email='second@example.com',browser_bridge_hash='hash')
        db=SimpleNamespace(get_token=AsyncMock(return_value=token),update_token=AsyncMock())
        flow=SimpleNamespace(get_request_fingerprint=lambda:None,_set_request_fingerprint=lambda value:None,
            get_credits=AsyncMock(side_effect=RuntimeError('private-session [rpc/http_400]')))
        manager=TokenManager(db,flow)
        with self.assertRaisesRegex(RuntimeError,r'rpc/http_400') as error: await manager.refresh_credits(8)
        self.assertNotIn('private-session',str(error.exception))
        self.assertEqual(db.update_token.await_args.args,(8,))
        self.assertNotIn('browser_bridge_hash',db.update_token.await_args.kwargs)
        self.assertNotIn('credits',db.update_token.await_args.kwargs)
