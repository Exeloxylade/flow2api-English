const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../browser-extension/page-bridge.js'), 'utf8');
function fixture() {
  const calls = [];
  const sandbox = {URL, URLSearchParams, AbortSignal, setTimeout, clearTimeout, setInterval, clearInterval,
    window: {WIZ_global_data: {oPEP7c: 'owner@example.com', cfb2h: 'build', FdrFJe: '123', SNlM0e: 'private-xsrf'}},
    location: {origin: 'https://flow.google.com', href: 'https://flow.google.com/projects'}, document: {documentElement: {innerHTML: ''}, querySelectorAll: () => [], querySelector: () => null},
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
  assert.equal(scripts[0].src, 'https://www.google.com/recaptcha/enterprise.js?render=6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV&trustedtypes=true');
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
  assert.equal((await f.run(captchaJob)).error_code, 'captcha_library_unavailable');
});

test('CAPTCHA checks account and action before loading any scripts', async () => {
  const f = fixture();
  f.sandbox.document.querySelectorAll = () => { throw new Error('should not inspect scripts'); };
  assert.equal((await f.run({...captchaJob, email: 'other@example.com'})).error_code, 'account_mismatch');
  assert.equal((await f.run({...captchaJob, action: 'arbitrary'})).error_code, 'invalid_operation');
});

test('CAPTCHA loader meets TrustedScriptURL enforcement and propagates the page nonce', async () => {
  const f = fixture();
  // An extension update must not reuse the old page policy, whose URL
  // allowlist rejected the new Google parameter. No page reload is required.
  f.sandbox.window.__flowConnectorCaptchaURLPolicy = {createScriptURL() {throw new Error('stale policy')}};
  let policyCount = 0;
  f.sandbox.window.trustedTypes = {createPolicy(name, rules) {
    assert.equal(name, 'flow-account-connector#recaptcha-v2');
    policyCount++;
    return {createScriptURL(value) { return {trusted: true, value: rules.createScriptURL(value)}; }};
  }};
  f.sandbox.document.querySelector = selector => { assert.equal(selector, 'script[nonce]'); return {nonce: 'page-nonce'}; };
  f.sandbox.document.createElement = () => ({set src(value) {assert.equal(value.trusted, true); this.url=value.value;}, remove() {}});
  f.sandbox.document.head = {appendChild(script) {
    assert.equal(script.nonce, 'page-nonce');
    assert.ok(script.url.startsWith('https://www.google.com/recaptcha/enterprise.js?render='));
    assert.equal(new URL(script.url).searchParams.get('trustedtypes'), 'true');
    f.sandbox.window.grecaptcha={enterprise:{ready: cb=>cb(),execute: async ()=>'verified-token'}};
  }};
  assert.equal((await f.run(captchaJob)).result.token, 'verified-token');
  const policy=f.sandbox.window.__flowConnectorCaptchaURLPolicyV2;
  for (const unsafe of ['https://evil.example/script.js','javascript:alert(1)','https://www.google.com/recaptcha/enterprise.js?render=123&extra=evil', 'https://www.google.com/recaptcha/enterprise.js?render=6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV', 'https://www.google.com/recaptcha/enterprise.js?render=6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV&trustedtypes=true&extra=evil']) {
    assert.throws(()=>policy.createScriptURL(unsafe));
  }
  delete f.sandbox.window.grecaptcha;
  assert.equal((await f.run(captchaJob)).success, true);
  assert.equal(policyCount, 1);
});

test('policy denial or script assignment failure cleans up and preserves page restrictions', async () => {
  for (const mode of ['policy_denied','assignment_failed']) {
    const f=fixture();
    let activePolls=0;
    f.sandbox.setInterval=(...args)=>{activePolls++; return setInterval(...args);};
    f.sandbox.clearInterval=id=>{activePolls--;clearInterval(id);};
    const originalFactory={createPolicy() {throw new TypeError('private CSP details');}};
    if (mode==='policy_denied') f.sandbox.window.trustedTypes=originalFactory;
    f.sandbox.document.createElement=()=>({set src(value) {throw new TypeError('TrustedScriptURL required');},remove(){}});
    f.sandbox.document.head={appendChild(){assert.fail('blocked script must not be appended');}};
    assert.equal((await f.run(captchaJob)).error_code, 'captcha_script_policy');
    assert.equal(activePolls, 0);
    assert.equal(f.sandbox.window.__flowConnectorCaptchaLoading, undefined);
    if (mode==='policy_denied') assert.equal(f.sandbox.window.trustedTypes, originalFactory);
  }
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


test('an existing failed loader reports promptly and preserves page handlers and script', async () => {
  const f=fixture(); let listener, removed=0; const handler=()=>{};
  const script={src:'https://www.google.com/recaptcha/enterprise.js', onerror:handler,
    addEventListener(type, callback) {assert.equal(type,'error');listener=callback},
    removeEventListener(type, callback) {assert.equal(type,'error');assert.equal(callback,listener); removed++},
    remove(){assert.fail('must preserve page script')}};
  f.sandbox.document.querySelectorAll=()=>[script];
  const result=f.run(captchaJob); listener();
  assert.equal((await result).error_code,'captcha_script_failed'); assert.equal(script.onerror,handler); assert.equal(removed,1);
});


test('both bootstrap and nested Google script obey Trusted Types without a default policy', async () => {
  const f=fixture(); const loaded=[], policies=[];
  const trusted = new WeakSet();
  f.sandbox.window.trustedTypes={createPolicy(name,rules) {
    assert.notEqual(name,'default'); policies.push(name);
    return {createScriptURL(value) { const result={url:rules.createScriptURL(value)}; trusted.add(result); return result }}
  }};
  f.sandbox.document.createElement=()=>({set src(value) {
    if (!trusted.has(value)) throw new TypeError('TrustedScriptURL required');
    this.url=value.url;
  },remove(){}});
  f.sandbox.document.head={appendChild(script) {
    loaded.push(script.url);
    // Model the two forms served by Google's bootstrap, not just an instantly ready API.
    const url='https://www.gstatic.com/recaptcha/releases/test/recaptcha__en.js';
    const child=f.sandbox.document.createElement('script');
    const ttMode=new URL(script.url).searchParams.get('trustedtypes')==='true';
    child.src=ttMode ? f.sandbox.window.trustedTypes.createPolicy('recaptcha',{createScriptURL:()=>url}).createScriptURL('') : url;
    loaded.push(child.url);
    f.sandbox.window.grecaptcha={enterprise:{ready: cb=>cb(),execute:async()=>'nested-loader-token'}};
  }};
  const result=await f.run(captchaJob);
  assert.equal(result.result.token,'nested-loader-token'); assert.equal(loaded.length,2);
  assert.deepEqual(policies,['flow-account-connector#recaptcha-v2','recaptcha']);
});
const captureSource=fs.readFileSync(require('node:path').join(__dirname,'../browser-extension/page-captcha.js'),'utf8');

test('startup integration uses the function Flow saved before public action replacement and restores bind', async () => {
  const f=fixture(), context=vm.createContext(f.sandbox);
  vm.runInContext('globalThis.savedBind = Function.prototype.bind; globalThis.savedAssign = Object.assign;',context);
  vm.runInContext(captureSource,context);
  vm.runInContext(`
    window.grecaptcha={enterprise:{ready: cb=>cb(),execute:function(key,options){
      if(this!==window.grecaptcha.enterprise) throw new Error('lost receiver');
      window.actualAction=options.action; return Promise.resolve('native-token');
    }}};
    window.flowSavedExecute=window.grecaptcha.enterprise.execute.bind(window.grecaptcha.enterprise);
    window.publicCalls=0;
    window.grecaptcha.enterprise.execute=function(key,options){
      window.publicCalls++;
      return window.flowSavedExecute(key,Object.assign({},options,{action:'extension_hijack_detected'}));
    };
    globalThis.bindRestored = Function.prototype.bind === savedBind;
    globalThis.assignUnchanged = Object.assign === savedAssign;
  `,context);
  vm.runInContext(source,context);
  const result=await context.runFlowOperation(captchaJob);
  assert.equal(result.result.token,'native-token'); assert.equal(result.result.execution_mode,'flow_saved_function'); assert.equal(context.window.actualAction,'IMAGE_GENERATION');
  assert.equal(context.window.publicCalls,0); assert.equal(context.bindRestored,true); assert.equal(context.assignUnchanged,true);
  const captured=context.window.__flowConnectorNativeCaptcha;
  vm.runInContext(captureSource,context); assert.equal(context.window.__flowConnectorNativeCaptcha,captured);
  assert.equal(vm.runInContext('Function.prototype.bind === savedBind',context),true);
});

test('late installation rejects the replaced public method without requesting an unusable token', async () => {
  const f=fixture(); let calls=0;
  f.sandbox.window.grecaptcha={enterprise:{ready: cb=>cb(),execute:function(key,options){
    calls++; return Promise.resolve(Object.assign({},options,{action:'extension_hijack_detected'}));
  }}};
  assert.equal((await f.run(captchaJob)).error_code,'captcha_native_reload_required');
  assert.equal(calls,0); assert.equal(f.calls.length,0);
});

test('startup integration ignores unrelated binds and never captures an already-replaced method', () => {
  const context=vm.createContext({window:{},location:{origin:'https://flow.google.com'}});
  vm.runInContext('globalThis.originalBind=Function.prototype.bind',context);
  vm.runInContext(captureSource,context);
  vm.runInContext(`
    function sum(a,b){return this.base+a+b;}
    globalThis.sumValue=sum.bind({base:10},2)(3);
    window.grecaptcha={enterprise:{execute:function(){return 'extension_hijack_detected'}}};
    window.grecaptcha.enterprise.execute.bind(window.grecaptcha.enterprise);
  `,context);
  assert.equal(context.sumValue,15);assert.equal(context.window.__flowConnectorNativeCaptcha,undefined);
  assert.equal(vm.runInContext('Function.prototype.bind === originalBind',context),false);
});

test('image reference uploads have an allowed CAPTCHA action', async () => {
  const f=fixture();let actual;
  f.sandbox.window.grecaptcha={enterprise:{ready:cb=>cb(),execute:async(_key,options)=>{actual=options.action;return 'upload-token'}}};
  assert.equal((await f.run({...captchaJob,action:'UPLOAD_IMAGE'})).result.token,'upload-token');assert.equal(actual,'UPLOAD_IMAGE');
});

test('startup capture is declared before page scripts in the main world on Flow only', () => {
  const manifest=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../browser-extension/manifest.json'),'utf8'));
  assert.equal(manifest.content_scripts.length,1);
  const script=manifest.content_scripts[0];
  assert.deepEqual(script.matches,['https://flow.google.com/*']);assert.deepEqual(script.js,['page-captcha.js']);
  assert.equal(script.world,'MAIN');assert.equal(script.run_at,'document_start');
});


test('video media lookup accepts its exact editor route without opening other RPC editor routes', async () => {
 const project='22222222-2222-2222-2222-222222222222', media='33333333-3333-3333-3333-333333333333'
 const f=fixture()
 const lookup={...f.job,rpc_id:'as29s',argument:[media],source_path:`/project/${project}/edit/${media}`}
 assert.equal((await f.run(lookup)).success,true)
 assert.equal(f.calls.length,1)
 assert.equal(new URL(f.calls[0].url,'https://flow.google.com').searchParams.get('source-path'),lookup.source_path)
 for(const change of [{rpc_id:'eb1hJf'},{source_path:`/project/${project}/edit/not-a-uuid`},{source_path:`/project/${project}/edit/${media}/extra`},{source_path:'https://attacker.example/edit'}]) {
  assert.equal((await f.run({...lookup,...change})).error_code,'invalid_operation')
 }
 assert.equal(f.calls.length,1)
})
