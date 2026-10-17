# Flow Account Connector

Install this extension once in the Chrome or Edge profile you use for Google Flow.

1. Extract the connector ZIP into a permanent folder.
2. Open `edge://extensions` or `chrome://extensions`.
3. Enable Developer mode, choose Load unpacked, and select the folder containing manifest.json.
4. In Bang Story or Flow2API, click Connect Google Flow and copy the pairing code.
5. Open Google Flow yourself in this browser profile, sign in and enter the creative studio.
6. Click this extension, paste the code, and click Connect this account. Keep the popup open until verification completes.
7. Keep that signed-in Flow studio tab open. The account panel should show **Browser online**; credits are checked automatically when the connection comes online.

Updating from connector 1.0.x: replace its extracted files with connector 1.1.2, click Reload on the extension card, and reconnect each account once with a fresh code. The older connector only copies cookies and cannot provide the live browser transport.

Updating from connector 1.1.0 or 1.1.1: overwrite the files in the same extracted folder with 1.1.2, then click Reload on its extension card. Keep the same extension installed so its pairing key remains saved; no new pairing code is needed. Version 1.1.2 loads the standard Google CAPTCHA library when it is missing, waits for readiness, and bounds execution time. It does not replace CAPTCHA methods or bypass Google verification. If Google rejects execution, test generation directly in the same Flow studio tab.

For another account, use its own Chrome/Edge profile, install the extension in that profile, and generate a fresh pairing code. Reconnect requires the same account. Codes expire after 10 minutes and are consumed after one submission. Cancelling in the app invalidates the code.

This extension reads Google session cookies only when you click Connect. They are sent directly to a paired server on 127.0.0.1, never an external extension server. Session cookies grant account access: use only a local Flow2API installation you trust. The extension stores a local pairing key, account identity and tab ID, without storing cookies or passwords. Credit, project, CAPTCHA and generation requests execute inside that signed-in tab. Every request checks its account identity first. Closing the tab makes the account unavailable without opening another browser or disabling the account. Reopening the matching signed-in Flow tab restores the connection automatically, including after a server restart. If Google requires sign-in, sign in normally in that tab. A new pairing is needed after removing the extension or replacing its stored connection key.

Version 1.1.2 also supports Flow pages that enforce TrustedScriptURL: its named Trusted Types policy accepts only the Google enterprise.js loader with a validated site key, and the script inherits the current page nonce. It does not install a default policy or weaken CSP. Synchronous loader failures release timers and report a script-loading error.
