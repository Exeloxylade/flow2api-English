"""Register browser sessions without exposing credentials in responses or errors."""

import hashlib
from datetime import datetime
from .browser_cookie_utils import validate_flow_cookie_storage
from .protocol_login import protocol_loginer


class BrowserSessionError(ValueError):
    """A deliberately safe error that can be returned to a desktop client."""


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
            raise BrowserSessionError("Reconnect must use the same existing Google account")

    # A client-provided email is not proof of identity. Verify the signed-in Flow page first.
    proxy = getattr(existing, "proxy_url", None) if existing else None
    verified = await protocol_loginer.login(google_cookies, proxy=proxy, email=email)
    if not verified.get("success") or str(verified.get("email", "")).strip().lower() != email:
        raise BrowserSessionError("Google Flow could not verify this account. Sign in again")
    cookies = str(verified.get("google_cookies") or "")
    try:
        validate_flow_cookie_storage(cookies)
    except (ValueError, OverflowError):
        raise BrowserSessionError("Google Flow returned incomplete session cookies") from None

    if existing:
        session = await manager.flow_client.st_to_at(
            existing.st, google_cookies=cookies, token_id=existing.id,
        )
        expires = session.get("expires")
        at_expires = datetime.fromisoformat(expires.replace("Z", "+00:00")) if expires else None
        await manager.update_token(
            existing.id,
            st="frontend-" + hashlib.sha256(cookies.encode("utf-8")).hexdigest()[:32],
            at=session["access_token"], at_expires=at_expires,
            email=email, login_account=email, google_cookies=cookies,
            protocol_mode="protocol", auto_refresh_enabled=True,
            refresh_interval_minutes=120,
        )
        if not existing.is_active:
            await manager.enable_token(existing.id)
        account = await manager.get_token(existing.id)
        action = "updated"
    else:
        account = await manager.add_token(
            st="", google_cookies=cookies, login_account=email,
            remark="Connected with browser login", protocol_mode="protocol",
            auto_refresh_enabled=True, refresh_interval_minutes=120,
        )
        action = "added"

    if concurrency_manager:
        await concurrency_manager.reset_token(
            account.id, image_concurrency=account.image_concurrency,
            video_concurrency=account.video_concurrency,
        )
    return {
        "success": True, "action": action,
        "account": {"id": account.id, "email": email, "enabled": bool(account.is_active)},
    }
