"""Firefox interface language for the dedicated TV profile, applied at the next startup."""

from pathlib import Path

LOCALES = ("ru", "en")
DEFAULT_LOCALE = "ru"
BEGIN = "// BEGIN AD-LINUX-TV LOCALE"
END = "// END AD-LINUX-TV LOCALE"
PREFS = {
    "ru": ('"ru"', '"ru-RU, ru, en-US, en"'),
    "en": ('"en-US"', '"en-US, en"'),
}


def validate_browser(value):
    if not isinstance(value, dict) or set(value) != {"locale"} or value["locale"] not in LOCALES:
        raise ValueError("browser.locale must be ru or en")
    return dict(value)


def browser_locale(config):
    return config.get("browser", {}).get("locale", DEFAULT_LOCALE)


def installed_locales(profile):
    """English is built in; other languages need a language pack in the dedicated profile."""
    extensions = Path(profile) / "extensions"
    return [
        locale
        for locale in LOCALES
        if locale == "en" or (extensions / f"langpack-{locale}@firefox.mozilla.org.xpi").is_file()
    ]


def replace_block(text, begin, end, body):
    """Return text with the managed begin/end block replaced by body, or removed for None."""
    kept = []
    inside = False
    for line in text.splitlines(keepends=True):
        if line.strip() == begin:
            if inside:
                raise ValueError("invalid managed preference block")
            inside = True
        elif line.strip() == end:
            if not inside:
                raise ValueError("invalid managed preference block")
            inside = False
        elif not inside:
            kept.append(line)
    if inside:
        raise ValueError("unterminated managed preference block")
    result = "".join(kept)
    if body is not None:
        if result and not result.endswith("\n"):
            result += "\n"
        result += f"{begin}\n{body}{end}\n"
    return result


def locale_profile_text(text, locale):
    requested, accepted = PREFS[locale]
    body = (
        f'user_pref("intl.locale.requested", {requested});\n'
        f'user_pref("intl.accept_languages", {accepted});\n'
    )
    return replace_block(text, BEGIN, END, body)
