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
    if (!response.ok) throw new FlowConnectorError(response.status === 401 || response.status === 409 ? 'Pairing expired, was cancelled, or could not verify this account. Create a fresh code in the app and retry.' : 'Flow2API could not accept the account. Check its dashboard and try again.');
    const value = await response.json();
    if (!value.success) throw new FlowConnectorError('The account was not connected. Check the app and retry.');
    return value.account;
  }
};
