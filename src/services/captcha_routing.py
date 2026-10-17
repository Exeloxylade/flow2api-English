"""Choose CAPTCHA independently from the account's RPC transport."""

CAPTCHA_METHODS = frozenset({
    "auto", "paired_browser", "personal", "browser", "extension",
    "remote_browser", "yescaptcha", "captcharun", "twocaptcha",
    "capmonster", "ezcaptcha", "capsolver",
})


def automatic_fallback_method(configured):
    return "personal" if configured in {"auto", "paired_browser"} else configured


def resolve_captcha_method(configured, *, paired, explicit=False, override=None):
    # Before provider selection was explicit, paired accounts always used their
    # tab. Preserve that default during upgrade, without hiding later choices.
    selected = override or (configured if explicit else "auto")
    if selected == "auto":
        selected = "paired_browser" if paired else automatic_fallback_method(configured)
    if selected not in CAPTCHA_METHODS:
        raise RuntimeError("Unsupported CAPTCHA method. Select a method in Settings > Captcha settings.")
    if selected == "paired_browser" and not paired:
        raise RuntimeError("Paired-browser CAPTCHA requires an account connected with Flow Account Connector.")
    return selected
