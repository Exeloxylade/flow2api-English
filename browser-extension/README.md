# Flow Account Connector

Install this extension once in the Chrome or Edge profile you use for Google Flow.

1. Extract the connector ZIP into a permanent folder.
2. Open `edge://extensions` or `chrome://extensions`.
3. Enable Developer mode, choose Load unpacked, and select the folder containing manifest.json.
4. In Bang Story or Flow2API, click Connect Google Flow and copy the pairing code.
5. Open Google Flow yourself in this browser profile, sign in and enter the creative studio.
6. Click this extension, paste the code, and click Connect this account. Keep the popup open until verification completes.

For another account, use its own Chrome/Edge profile, install the extension in that profile, and generate a fresh pairing code. Reconnect requires the same account. Codes expire after 10 minutes and are consumed after one submission. Cancelling in the app invalidates the code.

This extension reads Google session cookies only when you click Connect. They are sent directly to a paired server on 127.0.0.1, never an external extension server. Session cookies grant account access: use only a local Flow2API installation you trust. The extension does not store cookies or passwords. Flow2API stores the session in its existing local database for renewal and generation. It never controls the Google sign-in browser.
