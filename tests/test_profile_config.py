"""Only marked view preferences in a temporary dedicated profile; no real profile."""

import pytest

from ad_linux_tv.profile_config import prepare_locale_profile, prepare_view_profile


def test_omitted_view_uses_mobile_default_without_rewriting_unrelated_preferences(tmp_path):
    path = tmp_path / "profile/user.js"
    config = {"services": [{"id": "one"}]}
    prepare_view_profile(config, path)
    assert 'user_pref("browser.zoom.siteSpecific", false);' in path.read_text()
    original = 'user_pref("network.proxy.type", 5);\n// preserve trailing whitespace  '
    path.write_text(original)
    prepare_view_profile(config, path)
    active = path.read_text()
    assert active.startswith(original)
    prepare_view_profile(config, path)
    assert path.read_text() == active
    assert config == {"services": [{"id": "one"}]}


def test_per_tab_scope_is_marked_idempotent_and_restores_original_preferences(tmp_path):
    path = tmp_path / "user.js"
    original = (
        'user_pref("network.proxy.type", 5);\nuser_pref("browser.zoom.siteSpecific", true);\n'
    )
    path.write_text(original)
    config = {
        "services": [{"view": {"mode": "mobile", "zoom": 200}}],
        "auth": {"verifier": "never-export"},
    }
    prepare_view_profile(config, path)
    active = path.read_text()
    assert active.startswith(original)
    assert 'user_pref("browser.zoom.siteSpecific", false);' in active
    assert "never-export" not in active and "mobile" not in active
    assert path.stat().st_mode & 0o777 == 0o600
    prepare_view_profile(config, path)
    assert path.read_text() == active
    # The new common mobile default still needs per-tab zoom for omitted views.
    prepare_view_profile({"services": [{}]}, path)
    assert path.read_text() == active
    # Removing all managed services retires only our marked block.
    prepare_view_profile({"services": []}, path)
    assert path.read_text() == original


def test_malformed_managed_block_does_not_truncate_unrelated_preferences(tmp_path):
    path = tmp_path / "user.js"
    text = '// BEGIN AD-LINUX-TV VIEW\nuser_pref("network.proxy.type", 5);\n'
    path.write_text(text)
    with pytest.raises(ValueError):
        prepare_view_profile({"services": [{}]}, path)
    assert path.read_text() == text


def test_startup_locale_block_defaults_to_russian_and_follows_config(tmp_path):
    path = tmp_path / "user.js"
    path.write_text('user_pref("network.proxy.type", 5);\n')
    prepare_locale_profile({"services": []}, path)
    text = path.read_text()
    assert text.startswith('user_pref("network.proxy.type", 5);\n')
    assert 'user_pref("intl.locale.requested", "ru");' in text
    prepare_locale_profile({"services": []}, path)
    assert path.read_text() == text
    prepare_locale_profile({"services": [], "browser": {"locale": "en"}}, path)
    text = path.read_text()
    assert 'user_pref("intl.locale.requested", "en-US");' in text
    assert '"ru"' not in text
