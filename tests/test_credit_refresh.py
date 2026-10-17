import unittest
from unittest.mock import AsyncMock

from src.core.models import Token
from src.services.token_manager import TokenManager


class PositionalCreditsClient:
    def __init__(self):
        self.request_fingerprint = None

    def get_request_fingerprint(self):
        return self.request_fingerprint

    def _set_request_fingerprint(self, fingerprint):
        self.request_fingerprint = fingerprint

    async def get_credits(self, at):
        if at != "valid-at":
            raise AssertionError("credit lookup did not use the validated access token")
        return {"credits": 42, "userPaygateTier": "PAYGATE_TIER_ONE"}


class CreditRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_credits_uses_supported_flow_client_signature(self):
        token = Token(id=7, st="session", at="valid-at", email="user@example.com")
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
        )


if __name__ == "__main__":
    unittest.main()
