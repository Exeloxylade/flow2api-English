"""Register browser sessions without exposing credentials in responses or errors."""

from .browser_cookie_utils import validate_flow_cookie_storage
from .protocol_login import protocol_loginer


class BrowserSessionError(ValueError):
    """A deliberately safe error that can be returned to a desktop client."""
    def __init__(self, message, code="account_verification_failed"):
        super().__init__(message)
        self.code = code


async def register_browser_session(
    manager, db, *, email, google_cookies, expected_account_id=None,
    concurrency_manager=None,
):
    """The caller serializes registrations to prevent duplicate email insertions."""
    email = email.strip().lower()
    existing = await db.get_token_by_email(email)
    if expected_account_id is not None:
        expected = await manager.get_token(expected_account_id)
        identity = str((expected.login_account or expected.email) if expected else "").strip().lower()
        if not expected or identity != email or not existing or existing.id != expected_account_id:
            raise BrowserSessionError("Reconnect must use the same existing Google account", "account_mismatch")

    # A client-provided email is not proof of identity. Verify the signed-in Flow page first.
    proxy = getattr(existing, "proxy_url", None) if existing else None
    verified = await protocol_loginer.login(google_cookies, proxy=proxy, email=email)
    if not verified.get("success"):
        code = verified.get("error_code", "account_verification_failed")
        messages = {
            "cookies_incomplete": "The Flow session cookies are incomplete. Open the signed-in Flow studio and reconnect.",
            "flow_signin_redirect": "Google rejected the transferred session and redirected the server to sign-in. Reopen the Flow studio and reconnect.",
            "flow_http_error": "Google Flow rejected the server's verification request. Check Flow access and your network.",
            "flow_frontend_changed": "Flow returned an unexpected page during verification. The server needs a frontend compatibility update.",
            "flow_identity_missing": "Flow did not return a signed-in identity to the server. Open the creative studio before reconnecting.",
            "account_mismatch": "The server sees a different Google account. Use a browser profile with the intended Flow account.",
            "flow_network_error": "The server could not reach Google Flow. Check its internet connection or proxy.",
        }
        raise BrowserSessionError(messages.get(code, "Google Flow could not verify this account."), code if code in messages else "account_verification_failed")
    if str(verified.get("email", "")).strip().lower() != email:
        raise BrowserSessionError("The server sees a different Google account. Use the intended account's browser profile.", "account_mismatch")
    cookies = str(verified.get("google_cookies") or "")
    try:
        validate_flow_cookie_storage(cookies)
    except (ValueError, OverflowError):
        raise BrowserSessionError("Google Flow returned incomplete session cookies", "cookies_incomplete") from None

    try:
        account = await manager.save_verified_browser_account(email, cookies, existing=existing)
    except Exception:
        raise BrowserSessionError("The verified account could not be saved to the local database. Check disk space and retry.", "account_save_failed") from None
    action = "updated" if existing else "added"

    if concurrency_manager:
        await concurrency_manager.reset_token(
            account.id, image_concurrency=account.image_concurrency,
            video_concurrency=account.video_concurrency,
        )
    return {
        "success": True, "action": action,
        "account": {"id": account.id, "email": email, "enabled": bool(account.is_active)},
    }
