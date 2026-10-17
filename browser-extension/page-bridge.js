/* Fixed operations executed in the paired tab; the server cannot supply JS or URLs. */
async function runFlowOperation(job) {
  try {
    const wiz = window.WIZ_global_data || {};
    if (location.origin !== 'https://flow.google.com') throw new Error('page_not_ready');
    const email = String(wiz.oPEP7c || '').trim().toLowerCase();
    if (!email) throw new Error('authentication_required');
    if (email !== String(job.email || '').toLowerCase()) throw new Error('account_mismatch');
    if (job.operation === 'captcha') {
      if (!['IMAGE_GENERATION', 'VIDEO_GENERATION'].includes(job.action)) throw new Error('invalid_operation');
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
      if (typeof window.grecaptcha?.enterprise?.execute !== 'function') {
        // Share only the loading promise across simultaneous jobs, never tokens.
        if (!window.__flowConnectorCaptchaLoading) {
          window.__flowConnectorCaptchaLoading = new Promise((resolve, reject) => {
            let script;
            let poll;
            let timer;
            let settled = false;
            const finish = error => {
              if (settled) return;
              settled = true;
              clearInterval(poll); clearTimeout(timer);
              if (script) script.onerror = null;
              if (error) { if (script) script.remove(); reject(error); }
              else resolve();
            };
            poll = setInterval(() => {
              if (typeof window.grecaptcha?.enterprise?.execute === 'function') finish();
            }, 100);
            timer = setTimeout(() => finish(new Error('captcha_script_failed')), 15000);
            if (!existing) {
              try {
                script = document.createElement('script');
                const url = 'https://www.google.com/recaptcha/enterprise.js?render=' + encodeURIComponent(siteKey);
                let scriptURL = url;
                if (window.trustedTypes) {
                  // A named policy for this one Google loader only. Do not
                  // install a permissive default policy or alter page CSP.
                  if (!window.__flowConnectorCaptchaURLPolicy) {
                    window.__flowConnectorCaptchaURLPolicy = window.trustedTypes.createPolicy('flow-account-connector#recaptcha', {
                      createScriptURL(value) {
                        if (!/^https:\/\/www\.google\.com\/recaptcha\/enterprise\.js\?render=[A-Za-z0-9_-]{20,100}$/.test(value)) throw new TypeError('Unsupported CAPTCHA script URL');
                        return value;
                      }
                    });
                  }
                  scriptURL = window.__flowConnectorCaptchaURLPolicy.createScriptURL(url);
                }
                const nonce = document.querySelector('script[nonce]')?.nonce;
                if (nonce) script.nonce = nonce;
                script.src = scriptURL;
                script.async = true;
                script.onerror = () => finish(new Error('captcha_script_failed'));
                (document.head || document.documentElement).appendChild(script);
              } catch {
                finish(new Error('captcha_script_failed'));
              }
            }
          }).finally(() => { delete window.__flowConnectorCaptchaLoading; });
        }
        await window.__flowConnectorCaptchaLoading;
      }
      const api = window.grecaptcha?.enterprise;
      const readyOwner = typeof api?.ready === 'function' ? api : window.grecaptcha;
      if (typeof api?.execute !== 'function' || typeof readyOwner?.ready !== 'function') throw new Error('captcha_unavailable');
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
        token = await bounded(() => api.execute(siteKey, {action: job.action}), 30000);
      } catch (error) {
        throw new Error(error.message === 'captcha_timeout' ? 'captcha_timeout' : 'captcha_rejected');
      }
      if (typeof token !== 'string' || !token.trim()) throw new Error('captcha_rejected');
      return {success: true, result: {token}};
    }
    const allowed = ['jHPbke', 'QI2zvc', 'nzlxg', 'as29s', 'cz8Z4b', 'maseQ', 'ogiZ0b', 'SPrCad', 'jwpduf', 'mrlkwd', 'GN0Bre', 'MZZa6b', 'nprQif', 'eb1hJf', 'fZytfe', 'p0UkFb', 'YhhmEf'];
    if (job.operation !== 'rpc' || !allowed.includes(job.rpc_id) || !Array.isArray(job.argument)) throw new Error('invalid_operation');
    if (!/^\/(projects|project\/[a-f0-9-]{36})$/i.test(job.source_path)) throw new Error('invalid_operation');
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
    const allowedErrors = ['authentication_required', 'account_mismatch', 'page_not_ready', 'captcha_unavailable', 'captcha_script_failed', 'captcha_timeout', 'captcha_rejected', 'invalid_operation'];
    return {success: false, error_code: allowedErrors.includes(error.message) ? error.message : 'request_failed'};
  }
}
