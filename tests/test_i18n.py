"""i18n catalog — the Python twin of the Go easybus-sdk/i18n tests (the same
cases, so all SDKs behave identically)."""
from easybus.i18n import BASE_LOCALE, Translator, base_lang, define_i18n, interpolate, resolve_schema, translate


def test_base_lang():
    cases = {"zh-CN": "zh", "zh_Hans": "zh", "ZH": "zh", "en": "en", "fr": "fr", " zh-TW ": "zh"}
    for inp, want in cases.items():
        assert base_lang(inp) == want, inp


def test_interpolate():
    assert interpolate("Hi {a} {b}", {"a": "1"}) == "Hi 1 {b}"
    assert interpolate("no params", None) == "no params"
    # A brace that is not a valid ident is left untouched.
    assert interpolate("{ }", None) == "{ }"


CATALOG = {
    "hello": {"en": "Hello {name}", "zh": "你好 {name}", "ja": "こんにちは {name}"},
    "plain": {"en": "plain", "zh": "简单"},
}


def test_translate():
    assert translate(CATALOG, "hello", "zh", {"name": "X"}) == "你好 X"
    assert translate(CATALOG, "hello", "zh-CN", {"name": "X"}) == "你好 X"
    assert translate(CATALOG, "hello", "ja-JP", {"name": "X"}) == "こんにちは X"
    # Unknown locale falls back to en.
    assert translate(CATALOG, "hello", "de", {"name": "X"}) == "Hello X"
    assert translate(CATALOG, "hello", "", {"name": "X"}) == "Hello X"
    # Unknown key returns the key.
    assert translate(CATALOG, "missing", "zh", None) == "missing"


def test_translator():
    tr = define_i18n(CATALOG)
    assert tr.t("zh", "plain") == "简单"
    assert tr.t("en", "plain") == "plain"
    assert tr.t("xx", "plain") == "plain"
    assert BASE_LOCALE == "en"


def test_resolve_schema():
    node = {
        "type": "object",
        "description": "root",
        "descriptions": {"zh": "根"},
        "properties": {"a": {"type": "string", "description": "A", "descriptions": {"zh": "甲"}}},
    }
    out = resolve_schema(node, "zh")
    assert out["description"] == "根"
    assert "descriptions" not in out
    assert out["properties"]["a"]["description"] == "甲"
    # English (no zh) keeps the base string.
    out_en = resolve_schema(node, "en")
    assert out_en["description"] == "root"
