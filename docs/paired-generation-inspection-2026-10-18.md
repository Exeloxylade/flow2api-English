# Flow2API generation inspection — 18 October 2026

Compared the user's fork and installed managed server with original `TheSmallHanCat/flow2api` main at `60e673b05fe2630189f49e6dd3b275c2c8599158` (16 October 2026). No user's browser was opened or inspected, and no live generation was submitted.

## Findings

| Area | Comparison and conclusion |
| --- | --- |
| Installed version | The inspected generation client, frontend builder, routing module and connector files matched the fork. This is not an old-source installation mismatch. |
| Failure stage | The five latest inspected requests reached 48% (submission), failed in 1.32–1.81 seconds, and returned `PUBLIC_ERROR_UNUSUAL_ACTIVITY`. They were no longer stuck loading the CAPTCHA library at 38%. |
| Image RPC and payload | `flow_frontend.py` matches upstream. AST comparisons confirm identical project context, `ogiZ0b` image argument builder, aspect ratio mapping, frame parser, error parser and response normalizer. |
| Original browser providers | `browser_captcha_personal.py`, `browser_captcha.py`, `browser_captcha_extension.py` and `recaptcha_runtime.py` matched upstream before this change. The original CaptchaWorker `extension/` also matched. |
| Active routing | Stored `personal` with `captcha_method_explicit=0` means Automatic. For the paired account, Automatic selected the custom `paired_browser` path, not the original personal worker. |
| Main compatibility gap | The custom connector called the public `grecaptcha.enterprise.execute` method. The original runtime documents that new Flow saves its bound method and replaces the public entry point with a wrapper that changes the action to `extension_hijack_detected`. The original personal worker installs a startup capture; the connector did not. |
| Offline reproduction | A page fixture requesting `IMAGE_GENERATION` through that replacement returned a non-empty token for `extension_hijack_detected`. Connector 1.1.5 incorrectly treated it as usable. A non-empty token therefore did not prove that the requested action was preserved or that Google would accept it. |
| Reference-image uploads | The server requests CAPTCHA action `UPLOAD_IMAGE`, but the connector allowlist accepted only image/video generation. This was a separate confirmed defect for uploads. |
| Account separation | The bridge dispatches by account ID, email, authenticated socket and request ID. Existing tests reject another account's socket response. No account crossover was found in this inspection. |
| Credit balance | Credits use a separate authenticated RPC and can succeed even when generation CAPTCHA is rejected. A successful credit refresh does not validate generation. |
| Retries | Paired image requests already avoid backend automatic resubmission and managed-browser fallback. Bang Story now cancels waiting jobs on unusual-activity rejection; already submitted jobs may finish. |
| Project context | The request includes the requested project/source path while execution uses the existing paired tab. This is not proof that every page-context check matches native Flow; no speculative project-navigation change was made. |
| Other divergence | The fork lacks upstream's latest relaxed-to-standard video model fallback. This is unrelated to the observed image CAPTCHA rejection and was not changed during this image-focused inspection. |

## Connector 1.1.6 change

The connector now installs a Flow-only MAIN-world script at document start. It captures the bound CAPTCHA function when Flow saves it, then immediately restores `Function.prototype.bind`. It does not replace the public execute method, modify `Object.assign`, create a permissive default policy, or retain CAPTCHA tokens. Each request executes separately after the existing account/action checks. This adapts the original startup capture rather than implementing its entire managed-browser subsystem in the extension.

If the page was loaded too early and only the known replaced method is available, the connector stops with `captcha_native_reload_required` instead of requesting a token for the wrong action. Reload the extension, then reload the existing signed-in Flow tab once. Pairing remains stored. The connector also accepts `UPLOAD_IMAGE`, and its download archive includes the new startup script.

Backend diagnostic logs contain only an allowlisted execution-mode label (`flow_saved_function`, `public_api`, or `unknown`), never the CAPTCHA token or arbitrary page values.

## Verification and limits

Offline fixtures cover startup capture, original receiver/action preservation, restored bind behavior, unrelated binds, late installation, upload action, manifest wiring and archive contents. Existing tests cover account routing, credits, explicit provider selection and generation payloads. The Google loader's Trusted Types compatibility fix remains in place.

**The active browser's wrapper was not inspected, and successful live generation is not verified.** The reproduction proves the compatibility defect and the correction under the modeled condition; it cannot prove that this is the only condition Google evaluates. If rejection persists after the existing tab is reloaded, the next evidence is the allowlisted execution-mode log, not another blind reconnect or automatic retry.

## Primary references

- [Original startup capture and action wrapper documentation](https://github.com/TheSmallHanCat/flow2api/blob/60e673b05fe2630189f49e6dd3b275c2c8599158/src/services/recaptcha_runtime.py)
- [Original personal worker execution](https://github.com/TheSmallHanCat/flow2api/blob/60e673b05fe2630189f49e6dd3b275c2c8599158/src/services/browser_captcha_personal.py)
- [Original image payload builder](https://github.com/TheSmallHanCat/flow2api/blob/60e673b05fe2630189f49e6dd3b275c2c8599158/src/services/flow_frontend.py)
- [Maintainer warning about browser CAPTCHA reliability](https://github.com/TheSmallHanCat/flow2api/issues/185)
