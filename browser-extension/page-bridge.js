/* Fixed operations executed in the paired tab; the server cannot supply JS or URLs. */
async function runFlowOperation(job) {
  try {
    const wiz = window.WIZ_global_data || {};
    if (location.origin !== 'https://flow.google.com') throw new Error('page_not_ready');
    const email = String(wiz.oPEP7c || '').trim().toLowerCase();
    if (!email) throw new Error('authentication_required');
    if (email !== String(job.email || '').toLowerCase()) throw new Error('account_mismatch');
    if (job.operation === 'captcha') {
      if (!['IMAGE_GENERATION', 'VIDEO_GENERATION', 'UPLOAD_IMAGE'].includes(job.action)) throw new Error('invalid_operation');
      // Credits do not load reCAPTCHA. Bootstrap the normal Google library in
      // this same signed-in tab, without replacing its methods or page hooks.
      let siteKey = '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV';
      const scripts = Array.from(document.querySelectorAll('script[src]'));
      const existing = scripts.find(script => {
        try {
          const url = new URL(script.src, location.href);
          return ['www.google.com', 'www.recaptcha.net'].includes(url.hostname) && url.pathname === '/recaptcha/enterprise.js';
        } catch { return false; }
      });
      if (existing) {
        const renderedKey = new URL(existing.src, location.href).searchParams.get('render');
        if (renderedKey && /^[A-Za-z0-9_-]{20,100}$/.test(renderedKey)) siteKey = renderedKey;
      }
      if (typeof window.__flowConnectorNativeCaptcha?.execute !== 'function' && typeof window.grecaptcha?.enterprise?.execute !== 'function') {
        // Share only the loading promise across simultaneous jobs, never tokens.
        if (!window.__flowConnectorCaptchaLoading) {
          window.__flowConnectorCaptchaLoading = new Promise((resolve, reject) => {
            let script;
            let poll;
            let timer;
            let settled = false;
            // A page-owned script must not be removed or have its handlers replaced.
            const existingError = () => finish(new Error('captcha_script_failed'));
            const finish = error => {
              if (settled) return;
              settled = true;
              clearInterval(poll); clearTimeout(timer);
              if (script) script.onerror = null;
              existing?.removeEventListener?.('error', existingError);
              if (error) { if (script) script.remove(); reject(error); }
              else resolve();
            };
            poll = setInterval(() => {
              if (typeof window.grecaptcha?.enterprise?.execute === 'function') finish();
            }, 100);
            timer = setTimeout(() => finish(new Error(existing ? 'captcha_library_unavailable' : 'captcha_script_failed')), 15000);
            existing?.addEventListener?.('error', existingError, {once: true});
            if (!existing) {
              try {
                script = document.createElement('script');
                // The Google bootstrap creates another script. Its Trusted Types mode
                // is required for that nested load as well as our first assignment.
                const url = 'https://www.google.com/recaptcha/enterprise.js?render=' + encodeURIComponent(siteKey) + '&trustedtypes=true';
                let scriptURL = url;
                if (window.trustedTypes) {
                  // A named policy for this one Google loader only. Do not
                  // install a permissive default policy or alter page CSP.
                  if (!window.__flowConnectorCaptchaURLPolicyV2) {
                    window.__flowConnectorCaptchaURLPolicyV2 = window.trustedTypes.createPolicy('flow-account-connector#recaptcha-v2', {
                      createScriptURL(value) {
                        if (!/^https:\/\/www\.google\.com\/recaptcha\/enterprise\.js\?render=[A-Za-z0-9_-]{20,100}&trustedtypes=true$/.test(value)) throw new TypeError('Unsupported CAPTCHA script URL');
                        return value;
                      }
                    });
                  }
                  scriptURL = window.__flowConnectorCaptchaURLPolicyV2.createScriptURL(url);
                }
                const nonce = document.querySelector('script[nonce]')?.nonce;
                if (nonce) script.nonce = nonce;
                script.src = scriptURL;
                script.async = true;
                script.onerror = () => finish(new Error('captcha_script_failed'));
                (document.head || document.documentElement).appendChild(script);
              } catch {
                finish(new Error('captcha_script_policy'));
              }
            }
          }).finally(() => { delete window.__flowConnectorCaptchaLoading; });
        }
        await window.__flowConnectorCaptchaLoading;
      }
      const captured = window.__flowConnectorNativeCaptcha;
      const api = captured?.enterprise || window.grecaptcha?.enterprise;
      const execute = typeof captured?.execute === 'function' ? captured.execute : api?.execute;
      if (!captured && typeof execute === 'function' && Function.prototype.toString.call(execute).includes('extension_hijack_detected')) throw new Error('captcha_native_reload_required');
      const readyOwner = typeof api?.ready === 'function' ? api : window.grecaptcha;
      if (typeof execute !== 'function' || typeof readyOwner?.ready !== 'function') throw new Error('captcha_unavailable');
      const bounded = (operation, timeout) => new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('captcha_timeout')), timeout);
        Promise.resolve().then(operation).then(resolve, reject).finally(() => clearTimeout(timer));
      });
      try {
        await bounded(() => new Promise(resolve => readyOwner.ready(resolve)), 10000);
      } catch (error) {
        throw new Error(error?.message === 'captcha_timeout' ? 'captcha_timeout' : 'captcha_unavailable');
      }
      let token;
      try {
        token = await bounded(() => execute.call(api, siteKey, {action: job.action}), 30000);
      } catch (error) {
        throw new Error(error.message === 'captcha_timeout' ? 'captcha_timeout' : 'captcha_rejected');
      }
      if (typeof token !== 'string' || !token.trim()) throw new Error('captcha_rejected');
      return {success: true, result: {token, execution_mode: captured ? 'flow_saved_function' : 'public_api'}};
    }
    const allowed = ['jHPbke', 'QI2zvc', 'nzlxg', 'as29s', 'cz8Z4b', 'maseQ', 'ogiZ0b', 'SPrCad', 'jwpduf', 'mrlkwd', 'GN0Bre', 'MZZa6b', 'nprQif', 'eb1hJf', 'fZytfe', 'p0UkFb', 'YhhmEf'];
    if (job.operation !== 'rpc' || !allowed.includes(job.rpc_id) || !Array.isArray(job.argument)) throw new Error('invalid_operation');
    const basePath = /^\/(projects|project\/[a-f0-9-]{36})$/i.test(job.source_path);
    const mediaPath = job.rpc_id === 'as29s' && /^\/project\/[a-f0-9-]{36}\/edit\/[a-f0-9-]{36}$/i.test(job.source_path);
    if (!basePath && !mediaPath) throw new Error('invalid_operation');
    const html = document.documentElement.innerHTML;
    const bl = String(wiz.cfb2h || html.match(/boq_labs-ai-sandbox-frontend_[A-Za-z0-9_.-]+/)?.[0] || '');
    const sid = String(wiz.FdrFJe || '');
    let xsrf = String(wiz.SNlM0e || '');
    if (!bl || !sid || !xsrf) throw new Error('page_not_ready');
    const query = new URLSearchParams({rpcids: job.rpc_id, 'source-path': job.source_path, bl, 'f.sid': sid, hl: 'en', _reqid: String(Math.floor(Math.random() * 80000) + 10000), rt: 'c'});
    const authuser = new URL(location.href).searchParams.get('authuser');
    if (authuser && /^\d+$/.test(authuser)) query.set('authuser', authuser);
    const url = '/_/AiSandboxAngularFrontend/data/batchexecute?' + query;
    for (let attempt = 0; attempt < 2; attempt++) {
      const body = new URLSearchParams({'f.req': JSON.stringify([[[job.rpc_id, JSON.stringify(job.argument), null, 'generic']]]), at: xsrf});
      const response = await fetch(url, {method: 'POST', credentials: 'include', redirect: 'error', headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8', 'x-same-domain': '1'}, body: body.toString(), signal: AbortSignal.timeout(120000)});
      if (response.status === 401 || response.status === 403) throw new Error('authentication_required');
      const text = await response.text();
      if (!response.ok) throw new Error('request_failed');
      const replacement = text.match(/\["xsrf"\s*,\s*"((?:\\.|[^"\\])*)"/);
      if (attempt === 0 && replacement) { xsrf = JSON.parse('"' + replacement[1] + '"'); continue; }
      return {success: true, result: {text}};
    }
    throw new Error('authentication_required');
  } catch (error) {
    const allowedErrors = ['authentication_required', 'account_mismatch', 'page_not_ready', 'captcha_native_reload_required', 'captcha_unavailable', 'captcha_script_failed', 'captcha_script_policy', 'captcha_library_unavailable', 'captcha_timeout', 'captcha_rejected', 'invalid_operation'];
    return {success: false, error_code: allowedErrors.includes(error.message) ? error.message : 'request_failed'};
  }
}
