# Flow Account Connector

Install this extension once in the Chrome or Edge profile you use for Google Flow.

1. Extract the connector ZIP into a permanent folder.
2. Open `edge://extensions` or `chrome://extensions`.
3. Enable Developer mode, choose Load unpacked, and select the folder containing manifest.json.
4. In Bang Story or Flow2API, click Connect Google Flow and copy the pairing code.
5. Open Google Flow yourself in this browser profile, sign in and enter the creative studio.
6. Click this extension, paste the code, and click Connect this account. Keep the popup open until verification completes.
7. Keep that signed-in Flow studio tab open. The account panel should show **Browser online**; credits are checked automatically when the connection comes online.

Updating from connector 1.0.x: replace its extracted files with connector 1.1.3, click Reload on the extension card, and reconnect each account once with a fresh code. The older connector only copies cookies and cannot provide the live browser transport.

Updating from connector 1.1.0 or 1.1.1: overwrite the files in the same extracted folder with 1.1.3, then click Reload on its extension card. Keep the same extension installed so its pairing key remains saved; no new pairing code is needed. Version 1.1.2 loads the standard Google CAPTCHA library when it is missing, waits for readiness, and bounds execution time. It does not replace CAPTCHA methods or bypass Google verification. If Google rejects execution, test generation directly in the same Flow studio tab.

For another account, use its own Chrome/Edge profile, install the extension in that profile, and generate a fresh pairing code. Reconnect requires the same account. Codes expire after 10 minutes and are consumed after one submission. Cancelling in the app invalidates the code.

This extension reads Google session cookies only when you click Connect. They are sent directly to a paired server on 127.0.0.1, never an external extension server. Session cookies grant account access: use only a local Flow2API installation you trust. The extension stores a local pairing key, account identity and tab ID, without storing cookies or passwords. Credit, project, CAPTCHA and generation requests execute inside that signed-in tab. Every request checks its account identity first. Closing the tab makes the account unavailable without opening another browser or disabling the account. Reopening the matching signed-in Flow tab restores the connection automatically, including after a server restart. If Google requires sign-in, sign in normally in that tab. A new pairing is needed after removing the extension or replacing its stored connection key.

Version 1.1.2 also supports Flow pages that enforce TrustedScriptURL: its named Trusted Types policy accepts only the Google enterprise.js loader with a validated site key, and the script inherits the current page nonce. It does not install a default policy or weaken CSP. Synchronous loader failures release timers and report a script-loading error.

Version 1.1.3 restores saved accounts independently, bounds identity checks on sleeping tabs, and prefers active Flow tabs when a saved tab is unavailable. A stale pairing cannot hold up another account.


CAPTCHA diagnostics (connector 1.1.4):
- `captcha_script_failed`: loading the Google library failed (including an existing page script's error event).
- `captcha_script_policy`: the page refused script creation or assignment. The connector preserves the page policy.
- `captcha_library_unavailable`: a page CAPTCHA loader exists but its public API did not appear within 15 seconds.
- `captcha_rejected`: the API was available but execution rejected or returned no token.

A connected account and a working credit balance do not prove CAPTCHA is available. Re-pairing does not repair page security restrictions or a rejected CAPTCHA. Select a separately configured CAPTCHA method in the dashboard if the paired page cannot supply it, or generate directly in Flow. No alternate method is guaranteed to be accepted by Google.


Connector 1.1.5 loads Google reCAPTCHA with `trustedtypes=true`. This enables Google's own narrow policy for its nested gstatic script. A TrustedScriptURL for the initial enterprise.js URL alone does not make that nested load compatible. No default policy is installed and page security is preserved. Reload the extension after updating its files; pairing is retained. This fixes a loader compatibility defect, but does not guarantee Google accepts a generated token.


Connector 1.1.6 aligns paired-tab CAPTCHA execution with the original Flow2API startup capture. Flow can save its own bound `enterprise.execute` function and then replace the public entry point. The connector captures that same bound function at document start, restores `Function.prototype.bind` immediately after capture, and does not change the public method or `Object.assign`.

After this update, reload the extension **and then reload your existing signed-in Flow tab once**. Keep the tab open until the studio loads. Pairing remains saved; no new browser/profile or account reconnection is required. A page loaded before the startup integration cannot retroactively supply the saved function. In that case the connector stops with `captcha_native_reload_required` instead of submitting a token from the known replaced method.

The backend logs `flow_saved_function` or `public_api` as a fixed execution-mode label, never the token. Reference image uploads now accept the server's `UPLOAD_IMAGE` CAPTCHA action. This integration is tested offline; Google's acceptance is not guaranteed by a non-empty token or a passing fixture.
