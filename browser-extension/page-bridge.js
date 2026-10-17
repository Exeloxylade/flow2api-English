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
      const api = window.grecaptcha?.enterprise;
      if (!api?.execute || !api?.ready) throw new Error('captcha_unavailable');
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('captcha_unavailable')), 10000);
        api.ready(() => { clearTimeout(timer); resolve(); });
      });
      const token = await api.execute('6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV', {action: job.action});
      if (!token) throw new Error('captcha_unavailable');
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
    const allowedErrors = ['authentication_required', 'account_mismatch', 'page_not_ready', 'captcha_unavailable', 'invalid_operation'];
    return {success: false, error_code: allowedErrors.includes(error.message) ? error.message : 'request_failed'};
  }
}
