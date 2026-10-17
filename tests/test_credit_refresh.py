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
