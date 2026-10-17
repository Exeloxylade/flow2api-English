/* Dashboard orchestration: login progress carries account metadata only. */
(() => {
    let state = null;
    let timer = null;
    let completedJob = null;
    const el = id => document.getElementById(id);
    async function request(path, body) {
        const response = await apiRequest(path, body === undefined ? {} : {method:'POST',body:JSON.stringify(body)});
        if (!response) return null;
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Setup is unavailable. Restart Flow2API and try again.');
        return data;
    }
    function render(value) {
        state = value;
        el('flowPairing').hidden = !value.pairing_code;
        el('flowPairingCode').value = value.pairing_code || '';
        el('flowSetupStatus').textContent = value.message;
        el('flowSetupStatus').setAttribute('role', value.phase === 'error' ? 'alert' : 'status');
        const supported = value.supported !== false;
        document.querySelectorAll('[data-flow-connect]').forEach(button => button.disabled = !!value.busy || !supported);
        el('flowConnectButton').textContent = value.busy ? (value.phase === 'preparing' ? 'Preparing…' : value.phase === 'saving' ? 'Finishing setup…' : 'Waiting for connector…') : (value.account || (typeof allTokens !== 'undefined' && allTokens.length) ? 'Add another Google account' : 'Connect Google Flow');
        el('flowCancelButton').hidden = !value.busy;
        el('flowCancelButton').disabled = value.phase === 'saving';
        el('flowSetupProgress').hidden = !value.busy || value.phase === 'login';
        document.querySelectorAll('[data-flow-step]').forEach(step => {
            step.classList.toggle('font-semibold', step.dataset.flowStep === value.phase);
        });
        if (value.busy && !timer) timer = setInterval(poll, 2000);
        if (!value.busy && timer) { clearInterval(timer); timer = null; }
        if (value.phase === 'ready' && completedJob !== value.job_id) {
            completedJob = value.job_id;
            void refreshTokens().then(() => { if (state.job_id === value.job_id) render(state); });
            void loadATAutoRefreshConfig();
        }
    }
    async function poll() {
        try { const value = await request('/api/browser-login/status'); if (value) render(value); }
        catch (error) {
            if (timer) { clearInterval(timer); timer = null; }
            el('flowSetupStatus').textContent = error.message;
            el('flowSetupStatus').setAttribute('role','alert');
            el('flowConnectButton').disabled = false;
            el('flowConnectButton').textContent = 'Retry connection';
        }
    }
    window.startGoogleFlowLogin = async function(accountId) {
        el('flowConnectButton').disabled = true;
        try {
            const value = await request('/api/browser-login/start', accountId ? {expected_account_id:accountId} : {});
            if (value) render(value);
        } catch (error) {
            el('flowSetupStatus').textContent = error.message;
            el('flowSetupStatus').setAttribute('role','alert');
            el('flowConnectButton').disabled = false;
            void poll();
        }
    };
    window.cancelGoogleFlowLogin = async function() {
        if (!state?.job_id) return;
        try { const value = await request('/api/browser-login/cancel', {job_id:state.job_id}); if (value) render(value); }
        catch (error) { el('flowSetupStatus').textContent = error.message; }
    };
    window.copyFlowPairingCode = async function() {
        try { await navigator.clipboard.writeText(el('flowPairingCode').value); }
        catch { el('flowPairingCode').focus(); el('flowPairingCode').select(); el('flowSetupStatus').textContent = 'Press Ctrl+C to copy the selected pairing code.'; }
    };
    window.addEventListener('DOMContentLoaded', poll);
    window.addEventListener('flow-accounts-updated', () => { if (state && !state.busy) void poll(); });
    window.addEventListener('beforeunload', () => { if (timer) clearInterval(timer); });
})();
