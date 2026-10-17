importScripts('page-bridge.js');

const connections = new Map();
let restoring = false;
const identityInTab = async id => {
  try {
    const [value] = await chrome.scripting.executeScript({target: {tabId: id}, world: 'MAIN', func: () => location.origin === 'https://flow.google.com' ? String(window.WIZ_global_data?.oPEP7c || '').trim().toLowerCase() : ''});
    return value?.result || '';
  } catch { return ''; }
};

async function findAccountTab(binding) {
  if (await identityInTab(binding.tab_id) === binding.email) return binding.tab_id;
  for (const tab of await chrome.tabs.query({url: 'https://flow.google.com/*'})) {
    if (await identityInTab(tab.id) === binding.email) return tab.id;
  }
  return null;
}

async function connectBinding(binding) {
  const key = `${binding.port}:${binding.account_id}`;
  if (connections.has(key)) return;
  const tabId = await findAccountTab(binding);
  if (!tabId) throw new Error('Flow tab unavailable');
  binding.tab_id = tabId;
  const socket = new WebSocket(`ws://127.0.0.1:${binding.port}/api/browser-session/ws`);
  connections.set(key, {socket, binding});
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { socket.close(); reject(new Error('Bridge unavailable')); }, 8000);
    let heartbeat;
    socket.onopen = () => socket.send(JSON.stringify({account_id: binding.account_id, secret: binding.secret}));
    socket.onmessage = async event => {
      let job;
      try { job = JSON.parse(event.data); } catch { return; }
      if (job.type === 'ready') {
        clearTimeout(timer);
        heartbeat = setInterval(() => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type: 'ping'})); }, 20000);
        resolve(); return;
      }
      if (job.type !== 'request' || typeof job.req_id !== 'string') return;
      let result = {success: false, error_code: 'page_not_ready'};
      try {
        if (job.email !== binding.email) throw new Error('Wrong account');
        const [value] = await chrome.scripting.executeScript({target: {tabId: binding.tab_id}, world: 'MAIN', func: runFlowOperation, args: [job]});
        if (value?.result) result = value.result;
      } catch { /* Browser exceptions may contain sensitive URLs. */ }
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({...result, req_id: job.req_id}));
    };
    socket.onerror = () => { clearTimeout(timer); reject(new Error('Bridge unavailable')); };
    socket.onclose = () => {
      clearTimeout(timer); clearInterval(heartbeat);
      if (connections.get(key)?.socket === socket) connections.delete(key);
      reject(new Error('Bridge closed'));
    };
  });
}

async function restoreBindings() {
  if (restoring) return;
  restoring = true;
  try {
    const {flowBridgeAccounts = {}} = await chrome.storage.local.get('flowBridgeAccounts');
    for (const binding of Object.values(flowBridgeAccounts)) {
      try { await connectBinding(binding); } catch { /* Wait for the signed-in tab; never open a new browser. */ }
    }
  } finally { restoring = false; }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || message?.type !== 'flow_bridge_connect') return;
  (async () => {
    const binding = message.binding;
    if (!binding || !Number.isInteger(binding.account_id) || !Number.isInteger(binding.port) || binding.port < 1024 || binding.port > 65535 || !/^[a-f0-9]{64}$/.test(binding.secret) || !Number.isInteger(binding.tab_id) || typeof binding.email !== 'string') throw new Error('Invalid binding');
    const key = `${binding.port}:${binding.account_id}`;
    const previous = connections.get(key);
    if (previous) { connections.delete(key); previous.socket.close(); }
    const {flowBridgeAccounts = {}} = await chrome.storage.local.get('flowBridgeAccounts');
    flowBridgeAccounts[key] = binding;
    await chrome.storage.local.set({flowBridgeAccounts});
    await connectBinding(binding);
    respond({success: true});
  })().catch(() => respond({success: false}));
  return true;
});
chrome.tabs.onRemoved.addListener(tabId => {
  for (const {socket, binding} of connections.values()) if (binding.tab_id === tabId) socket.close();
});
chrome.tabs.onUpdated.addListener((_id, change) => { if (change.status === 'complete') void restoreBindings(); });
chrome.alarms.create('flowBridgeReconnect', {periodInMinutes: 1});
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'flowBridgeReconnect') void restoreBindings(); });
chrome.runtime.onStartup.addListener(restoreBindings);
void restoreBindings();
