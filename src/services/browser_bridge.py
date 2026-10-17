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
                "email": email, **payload,
            })
            response = await asyncio.wait_for(future, timeout=timeout)
            if not response.get("success"):
                # Never echo a browser exception/URL/body into account logs.
                code = response.get("error_code")
                messages = {
                    "account_mismatch": "The paired Flow tab is signed in to a different account. Open the matching account's tab.",
                    "page_not_ready": "The paired Flow studio is not ready. Open its creative studio and leave the tab open.",
                    "authentication_required": "Google requires sign-in in the paired Flow tab. Sign in there, then retry.",
                    "captcha_unavailable": "The paired Flow tab could not provide CAPTCHA. Open the creative studio and retry.",
                    "captcha_script_failed": "Google's CAPTCHA library could not load in the paired Flow tab. Check that tab for blocked scripts or network errors, reload it, then retry. Pairing is still saved.",
                    "captcha_timeout": "Google's CAPTCHA did not finish in the paired Flow tab. Bring that tab to the foreground, complete any verification shown there, then retry.",
                    "captcha_rejected": "Google's CAPTCHA API rejected the request or returned no token in the paired Flow tab. Try generating directly in that tab to check Google's verification. Re-pairing will not fix a CAPTCHA rejection.",
                }
                raise RuntimeError(messages.get(code, "The request failed inside the paired Flow tab. Check that tab and retry."))
            return response.get("result")
        except asyncio.TimeoutError:
            raise RuntimeError("The paired Flow tab did not respond in time. Check that it is open and responsive.") from None
        finally:
            self.pending.pop(req_id, None)


browser_bridge = BrowserBridge()
