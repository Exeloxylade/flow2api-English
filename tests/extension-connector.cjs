const {test} = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const source = fs.readFileSync(path.join(__dirname, '../browser-extension/connector.js'), 'utf8')
function fixture() {
  const sandbox = {URL, AbortSignal}
  vm.runInNewContext(source, sandbox)
  const calls = []
  const state = {url: 'https://flow.google.com/projects', email: 'owner@example.com', code: 200, error_code: 'pairing_invalid'}
  const api = {
    tabs: {query: async () => [{id: 7, url: state.url}]},
    scripting: {executeScript: async () => [{result: {host: 'flow.google.com', email: state.email}}]},
    cookies: {
      getAllCookieStores: async () => [{id: 'wrong', tabIds: [8]}, {id: 'correct-profile', tabIds: [7]}],
      getAll: async options => {
        assert.equal(options.storeId, 'correct-profile')
        return [{name: 'OSID', domain: 'flow.google.com', value: 'private-session'}, {name: 'SID', domain: '.google.com', value: 'private-account'}, {name: 'wrong', domain: '.evilgoogle.com', value: 'private-other'}, {name: 'partitioned', domain: '.google.com', partitionKey: {}, value: 'private-other'}]
      }
    }
  }
  const fetcher = async (url, options) => {calls.push({url, options}); return {ok: state.code === 200, status: state.code, json: async () => state.code === 200 ? {success: true, account: {id: 3, email: state.email}} : {error_code: state.error_code, detail: 'private-session-data'}}}
  return {connector: sandbox.flowConnector, api, fetcher, state, calls, code: '8765:' + 'a'.repeat(64)}
}
test('connector reads the active browser profile only on explicit connect and sends only to loopback', async () => {
  const f = fixture()
  assert.equal(f.calls.length, 0)
  const account = await f.connector.connect(f.code, f.api, f.fetcher)
  assert.equal(account.email, f.state.email)
  assert.equal(f.calls[0].url, 'http://127.0.0.1:8765/api/browser-login/extension')
  assert.equal(f.calls[0].options.redirect, 'error')
  assert.equal(f.calls[0].options.credentials, 'omit')
  const body = JSON.parse(f.calls[0].options.body)
  assert.equal(body.login_account, f.state.email)
  assert.deepEqual(JSON.parse(body.google_cookies).map(c => c.name), ['OSID', 'SID'])
})
test('remote endpoints, malformed pairings and non-Flow tabs never receive credentials', async () => {
  const f = fixture()
  for (const code of ['https://evil.example:' + 'a'.repeat(64), '80:' + 'a'.repeat(64), '99999:' + 'a'.repeat(64), '8765:short']) await assert.rejects(f.connector.connect(code, f.api, f.fetcher))
  for (const url of ['https://flow.google.com.evil.example', 'http://flow.google.com', 'https://accounts.google.com']) {
    f.state.url = url
    await assert.rejects(f.connector.connect(f.code, f.api, f.fetcher), /studio tab/)
  }
  assert.equal(f.calls.length, 0)
})
test('an unsigned-in page does not export cookies and expired pairing gives a fixed error', async () => {
  const f = fixture()
  f.state.email = ''
  await assert.rejects(f.connector.connect(f.code, f.api, f.fetcher), /Sign in/)
  assert.equal(f.calls.length, 0)
  f.state.email = 'owner@example.com'
  f.state.code = 409
  await assert.rejects(f.connector.connect(f.code, f.api, f.fetcher), /already used/)
})
test('accepted-code verification failures are distinct from expiry and server text cannot leak credentials', async () => {
  const f = fixture()
  f.state.code = 409
  f.state.error_code = 'flow_signin_redirect'
  await assert.rejects(f.connector.connect(f.code, f.api, f.fetcher), error => /pairing code was accepted/.test(error.message) && !error.message.includes('private-'))
  f.state.error_code = '__proto__'
  await assert.rejects(f.connector.connect(f.code, f.api, f.fetcher), error => /specific failure reason/.test(error.message) && !error.message.includes('private-'))
})
