/* Capture the same bound CAPTCHA function Flow saves during startup.
 * Adapted from upstream recaptcha_runtime.py. Restore bind after capture;
 * never replace enterprise.execute or alter Object.assign/page policies.
 */
(() => {
  if (location.origin !== 'https://flow.google.com' || window.__flowConnectorCaptureInstalled) return;
  window.__flowConnectorCaptureInstalled = true;
  const originalBind = Function.prototype.bind;
  const functionSource = Function.prototype.toString;
  function observeBind(thisArg, ...args) {
    const bound = Reflect.apply(originalBind, this, [thisArg, ...args]);
    try {
      const enterprise = window.grecaptcha?.enterprise;
      if (!window.__flowConnectorNativeCaptcha && enterprise && this === enterprise.execute &&
          !Reflect.apply(functionSource, this, []).includes('extension_hijack_detected')) {
        window.__flowConnectorNativeCaptcha = Object.freeze({execute: bound, enterprise});
        if (Function.prototype.bind === observeBind) Function.prototype.bind = originalBind;
      }
    } catch { /* Preserve the page's original bind result even if inspection fails. */ }
    return bound;
  }
  Function.prototype.bind = observeBind;
})();
