"""Authenticated, account-bound transport to the user's signed-in Flow tab."""

import asyncio
import uuid


class BrowserBridge:
    def __init__(self):
        self.connections = {}
        self.pending = {}

    def is_online(self, account_id):
        return int(account_id) in self.connections

    async def attach(self, account_id, websocket):
        account_id = int(account_id)
        previous = self.connections.get(account_id)
        if previous is not None and previous is not websocket:
            try:
                await previous.close(code=1000)
            except Exception:
                pass
        self.connections[account_id] = websocket
        await websocket.send_json({"type": "ready"})

    async def revoke(self, account_id):
        socket = self.connections.get(int(account_id))
        if socket:
            self.detach(account_id, socket)
            try:
                await socket.close(code=1000)
            except Exception:
                pass

    def detach(self, account_id, websocket):
        if self.connections.get(int(account_id)) is websocket:
            self.connections.pop(int(account_id), None)
        for future, owner in list(self.pending.values()):
            if owner is websocket and not future.done():
                future.set_exception(RuntimeError("The paired Flow tab disconnected. Reopen that account's Flow tab."))

    def receive(self, websocket, message):
        pending = self.pending.get(message.get("req_id"))
        if pending:
            future, owner = pending
            if owner is websocket and not future.done():
                future.set_result(message)

    async def call(self, account_id, email, operation, *, timeout=120, **payload):
        socket = self.connections.get(int(account_id))
        if socket is None:
            raise RuntimeError("The paired Flow browser is offline. Open the signed-in Flow tab with Flow Account Connector enabled.")
        req_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[req_id] = (future, socket)
        try:
            await socket.send_json({
                "type": "request", "req_id": req_id, "operation": operation,
                "email": email, "timeout_ms": max(250, int(timeout * 1000)), **payload,
            })
            response = await asyncio.wait_for(future, timeout=timeout)
            if not response.get("success"):
                # Never echo a browser exception/URL/body into account logs.
                code = response.get("error_code")
                messages = {
                    "network_error": "The paired Flow tab could not reach Google. Check that profile's network, proxy, and blocking extensions.",
                    "http_400": "Google rejected the paired tab request (HTTP 400). Refresh that account's studio to renew its page session.",
                    "http_404": "The Flow request endpoint was not found (HTTP 404). Refresh the studio and check connector compatibility.",
                    "http_409": "Google reported a conflicting Flow request (HTTP 409). Wait and check the studio.",
                    "http_429": "Google rate limited this Flow account (HTTP 429). Wait before checking again.",
                    "http_500": "Google Flow returned a server error (HTTP 500). Try checking again later.",
                    "http_502": "Google Flow returned a gateway error (HTTP 502). Try checking again later.",
                    "http_503": "Google Flow is temporarily unavailable (HTTP 503). Try checking again later.",
                    "account_mismatch": "The paired Flow tab is signed in to a different account. Open the matching account's tab.",
                    "request_timeout": "The paired Flow tab request timed out. Its outcome is unknown; check the existing Flow task before retrying. Reload an unresponsive Flow tab.",
                    "page_not_ready": "The paired Flow studio is not ready. Open its creative studio and leave the tab open.",
                    "authentication_required": "Google requires sign-in in the paired Flow tab. Sign in there, then retry.",
                    "captcha_native_reload_required": "The Flow page replaced its public CAPTCHA function. Reload the connector extension, then reload this existing Flow tab once so the startup integration can initialize. Pairing is still saved.",
                    "captcha_unavailable": "The paired Flow tab could not provide CAPTCHA. Open the creative studio and retry.",
                    "captcha_script_failed": "Google's CAPTCHA library could not load in the paired Flow tab. Check that tab for blocked scripts or network errors, reload it, then retry. Pairing is still saved.",
                    "captcha_script_policy": "The Flow page's security policy prevented the connector from loading CAPTCHA. Pairing and credits can still work. Re-pairing does not change this policy; use another configured CAPTCHA method or generate directly in Flow.",
                    "captcha_library_unavailable": "The Flow page contains a CAPTCHA loader but its public API did not become available. The connector cannot use it in this page. Re-pairing does not fix this; select another supported CAPTCHA method or generate directly in Flow.",
                    "captcha_timeout": "Google's CAPTCHA did not finish in the paired Flow tab. Bring that tab to the foreground, complete any verification shown there, then retry.",
                    "captcha_rejected": "Google's CAPTCHA API rejected the request or returned no token in the paired Flow tab. Try generating directly in that tab to check Google's verification. Re-pairing will not fix a CAPTCHA rejection.",
                }
                safe_codes = set(messages) | {"request_failed", "invalid_operation"}
                safe_code = code if isinstance(code, str) and code in safe_codes else "unknown_error"
                step = "captcha" if operation == "captcha" else "rpc" if operation == "rpc" else "request"
                message = messages.get(safe_code, "The request failed inside the paired Flow tab. Check that tab and retry.")
                raise RuntimeError(f"{message} [{step}/{safe_code}]")
            return response.get("result")
        except asyncio.TimeoutError:
            raise RuntimeError("The paired Flow tab did not respond in time. Check that it is open and responsive.") from None
        finally:
            self.pending.pop(req_id, None)


browser_bridge = BrowserBridge()
