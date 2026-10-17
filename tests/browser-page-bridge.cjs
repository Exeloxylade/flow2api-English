const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../browser-extension/page-bridge.js'), 'utf8');
function fixture() {
  const calls = [];
  const sandbox = {URL, URLSearchParams, AbortSignal, setTimeout, clearTimeout, setInterval, clearInterval,
    window: {WIZ_global_data: {oPEP7c: 'owner@example.com', cfb2h: 'build', FdrFJe: '123', SNlM0e: 'private-xsrf'}},
    location: {origin: 'https://flow.google.com', href: 'https://flow.google.com/projects'}, document: {documentElement: {innerHTML: ''}, querySelectorAll: () => []},
    fetch: async (url, options) => { calls.push({url, options}); return {status: 200, ok: true, text: async () => 'response-frames'}; }};
  vm.runInNewContext(source, sandbox);
  return {sandbox, calls, run: sandbox.runFlowOperation, job: {operation: 'rpc', rpc_id: 'nzlxg', argument: [], source_path: '/projects', email: 'owner@example.com'}};
}
test('RPC executes with current browser credentials and XSRF without reading exported cookies', async () => {
  const f = fixture();
  const result = await f.run(f.job);
  assert.equal(result.success, true);
  assert.equal(f.calls.length, 1);
  assert.ok(f.calls[0].url.startsWith('/_/AiSandboxAngularFrontend/'));
  assert.equal(f.calls[0].options.credentials, 'include');
  assert.equal(new URLSearchParams(f.calls[0].options.body).get('at'), 'private-xsrf');
});

const captchaJob = {operation: 'captcha', action: 'IMAGE_GENERATION', email: 'owner@example.com'};

test('CAPTCHA loads the Google library once for concurrent jobs and executes each separately in the paired page', async () => {
  const f = fixture();
  const scripts = [], executions = [];
  f.sandbox.document.createElement = () => ({remove() {}});
  f.sandbox.document.head = {appendChild(script) {
    scripts.push(script);
    f.sandbox.window.grecaptcha = {enterprise: {
      ready(callback) { assert.equal(this, f.sandbox.window.grecaptcha.enterprise); callback(); },
      execute(key, options) { executions.push({key, action: options.action}); return Promise.resolve('token-' + executions.length); }
    }};
  }};
  const results = await Promise.all([f.run(captchaJob), f.run(captchaJob)]);
  assert.equal(scripts.length, 1);
  assert.equal(scripts[0].src, 'https://www.google.com/recaptcha/enterprise.js?render=6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV');
  assert.ok(results.every(value => value.success));
  assert.notEqual(results[0].result.token, results[1].result.token);
  assert.equal(executions.length, 2);
  assert.ok(executions.every(value => value.action === 'IMAGE_GENERATION'));
  assert.equal(f.sandbox.window.__flowConnectorCaptchaLoading, undefined);
  assert.equal(f.calls.length, 0);
});

test('CAPTCHA waits for an existing page script and uses its rendered site key without injecting duplicates', async () => {
  const f = fixture();
  const key = 'page-site-key-1234567890';
  f.sandbox.document.querySelectorAll = () => [{src: 'https://www.google.com/recaptcha/enterprise.js?render=' + key}];
  f.sandbox.document.createElement = () => { throw new Error('duplicate script'); };
  setTimeout(() => { f.sandbox.window.grecaptcha = {enterprise: {
    ready: callback => callback(), execute: async supplied => { assert.equal(supplied, key); return 'page-token'; }
  }}; }, 10);
  assert.equal((await f.run(captchaJob)).result.token, 'page-token');
});

test('CAPTCHA supports root ready and does not replace the page execute function', async () => {
  const f = fixture();
  const execute = async () => 'root-ready-token';
  f.sandbox.window.grecaptcha = {ready(callback) { assert.equal(this, f.sandbox.window.grecaptcha); callback(); }, enterprise: {execute}};
  assert.equal((await f.run(captchaJob)).result.token, 'root-ready-token');
  assert.equal(f.sandbox.window.grecaptcha.enterprise.execute, execute);
});

test('blocked CAPTCHA script is reported safely and can be retried without pairing again', async () => {
  const f = fixture();
  let removed = 0;
  f.sandbox.document.createElement = () => ({remove() { removed++; }});
  f.sandbox.document.head = {appendChild(script) { queueMicrotask(() => script.onerror()); }};
  for (let attempt = 0; attempt < 2; attempt++) {
    assert.equal((await f.run(captchaJob)).error_code, 'captcha_script_failed');
    assert.equal(f.sandbox.window.__flowConnectorCaptchaLoading, undefined);
  }
  assert.equal(removed, 2);
});

test('CAPTCHA rejection and empty tokens never become a successful generation or leak browser exceptions', async () => {
  const f = fixture();
  for (const execute of [async () => { throw new Error('private page details'); }, async () => '', async () => null]) {
    f.sandbox.window.grecaptcha = {enterprise: {ready: callback => callback(), execute}};
    const result = await f.run(captchaJob);
    assert.equal(result.error_code, 'captcha_rejected');
    assert.equal(JSON.stringify(result).includes('private'), false);
  }
});

test('CAPTCHA execution and library loading both have bounded waits', async () => {
  const f = fixture();
  f.sandbox.setTimeout = callback => setTimeout(callback, 5);
  f.sandbox.window.grecaptcha = {enterprise: {ready: callback => callback(), execute: () => new Promise(() => {})}};
  assert.equal((await f.run(captchaJob)).error_code, 'captcha_timeout');
  delete f.sandbox.window.grecaptcha;
  f.sandbox.document.querySelectorAll = () => [{src: 'https://www.google.com/recaptcha/enterprise.js'}];
  assert.equal((await f.run(captchaJob)).error_code, 'captcha_script_failed');
});

test('CAPTCHA checks account and action before loading any scripts', async () => {
  const f = fixture();
  f.sandbox.document.querySelectorAll = () => { throw new Error('should not inspect scripts'); };
  assert.equal((await f.run({...captchaJob, email: 'other@example.com'})).error_code, 'account_mismatch');
  assert.equal((await f.run({...captchaJob, action: 'arbitrary'})).error_code, 'invalid_operation');
});
test('wrong account and arbitrary RPC/path never execute a request', async () => {
  const f = fixture();
  assert.equal((await f.run({...f.job, email: 'other@example.com'})).error_code, 'account_mismatch');
  assert.equal((await f.run({...f.job, rpc_id: 'arbitrary'})).success, false);
  assert.equal((await f.run({...f.job, source_path: 'https://evil.example'})).success, false);
  assert.equal(f.calls.length, 0);
});
test('missing real browser session token reports not-ready instead of pretending connected', async () => {
  const f = fixture(); delete f.sandbox.window.WIZ_global_data.SNlM0e;
  assert.equal((await f.run(f.job)).error_code, 'page_not_ready');
  assert.equal(f.calls.length, 0);
});
