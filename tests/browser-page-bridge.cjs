const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../browser-extension/page-bridge.js'), 'utf8');
function fixture() {
  const calls = [];
  const sandbox = {URL, URLSearchParams, AbortSignal, setTimeout, clearTimeout,
    window: {WIZ_global_data: {oPEP7c: 'owner@example.com', cfb2h: 'build', FdrFJe: '123', SNlM0e: 'private-xsrf'}},
    location: {origin: 'https://flow.google.com', href: 'https://flow.google.com/projects'}, document: {documentElement: {innerHTML: ''}},
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
