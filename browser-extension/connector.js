/* No content scripts, background collection, persistent storage, or debugger access. */
class FlowConnectorError extends Error {}
globalThis.flowConnector = {
  parseCode(value) {
    const match = /^(\d{1,5}):([a-f0-9]{64})$/.exec(value.trim());
    if (!match || Number(match[1]) < 1024 || Number(match[1]) > 65535) throw new FlowConnectorError('Copy a fresh pairing code from Bang Story or Flow2API.');
    return {url: `http://127.0.0.1:${Number(match[1])}/api/browser-login/extension`, token: match[2]};
  },
  async connect(code, api = chrome, fetcher = fetch) {
    const pairing = this.parseCode(code);
    const [tab] = await api.tabs.query({active: true, currentWindow: true});
    if (!tab?.id || !tab.url || new URL(tab.url).origin !== 'https://flow.google.com') throw new FlowConnectorError('Open the signed-in Google Flow studio tab, then reopen this extension.');
    const results = await api.scripting.executeScript({target: {tabId: tab.id}, world: 'MAIN', func: () => ({host: location.hostname, email: String((window.WIZ_global_data || {}).oPEP7c || '').trim().toLowerCase()})});
    const identity = results[0]?.result;
    if (identity?.host !== 'flow.google.com' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identity.email)) throw new FlowConnectorError('Sign in, click Create with Google Flow, and wait for the studio to load before connecting.');
    const stores = await api.cookies.getAllCookieStores();
    const store = stores.find(item => item.tabIds.includes(tab.id));
    if (!store) throw new FlowConnectorError('The browser profile could not be identified. Reopen this extension on the Flow tab.');
    const cookies = (await api.cookies.getAll({domain: 'google.com', storeId: store.id})).filter(cookie => {
      const host = cookie.domain.replace(/^\./, '');
      return (host === 'google.com' || host.endsWith('.google.com')) && !cookie.partitionKey;
    });
    if (!cookies.some(c => ['OSID', '__Secure-OSID'].includes(c.name))) throw new FlowConnectorError('The Flow session is incomplete. Sign in to the Flow studio before connecting.');
    const response = await fetcher(pairing.url, {
      method: 'POST', credentials: 'omit', redirect: 'error',
      headers: {'Content-Type': 'application/json', 'X-Flow-Connector': '1', Authorization: `Bearer ${pairing.token}`},
      body: JSON.stringify({login_account: identity.email, google_cookies: JSON.stringify(cookies)}),
      signal: AbortSignal.timeout(125000)
    });
    if (!response.ok) {
      const problem = await response.json().catch(() => ({}));
      const messages = {
        pairing_invalid: 'The code is expired, cancelled, or already used. Copy a NEW code from Bang Story, then retry once.',
        account_mismatch: 'Flow2API sees a different Google account. Use a browser profile signed in to the intended Flow account.',
        cookies_incomplete: 'The session is incomplete. Open your signed-in Flow studio before connecting.',
        flow_signin_redirect: 'Google rejected the transferred session and redirected Flow2API to sign-in. The pairing code was accepted.',
        flow_http_error: 'Google Flow rejected verification from the local server. Check Flow access and the server network.',
        flow_frontend_changed: 'Flow2API received an unexpected Flow page. The server needs a compatibility update.',
        flow_identity_missing: 'Flow2API could not verify an account in the returned Flow page. Open the creative studio and reconnect.',
        flow_network_error: 'The local server could not reach Google Flow. Check its internet connection or proxy.',
        account_save_failed: 'The account was verified, but Flow2API could not save it. Check local disk space.',
        verification_timeout: 'Flow verification timed out. Check the server connection and create a new code.',
        account_setup_failed: 'The pairing code was accepted, but local account setup failed. Update Flow2API and retry with a new code.',
        local_configuration_failed: 'The account was saved, but server settings failed to update. Restart Flow2API and check the account list.',
        account_verification_failed: 'The code was accepted, but Google Flow did not verify the session. Open the intended Flow studio and create a new code.'
      };
      const message = Object.hasOwn(messages, problem.error_code) ? messages[problem.error_code] : response.status === 401 ? messages.pairing_invalid : 'Flow2API did not return a specific failure reason. Update the app and server, create a new code, and retry once.';
      throw new FlowConnectorError(message);
    }
    const value = await response.json();
    if (!value.success) throw new FlowConnectorError('The account was not connected. Check the app and retry.');
    return value.account;
  }
};
