"""Localization — the Python twin of the Go `easybus-sdk/i18n` package and the
TypeScript `easybus-sdk` i18n core. Typed, extensible-locale localisation for
extension-authored strings that reach the model context.

Tool DESCRIPTIONS are localized through the manifest (`description` +
`descriptions[locale]`). This module covers the OTHER half: the runtime
`content` and error text a tool returns, which is fed verbatim to the model.

Design (mirrors the Go/TS cores so all SDKs behave identically):

  - A Catalog is ``{key: {locale: template}}``. The locale set is an OPEN map
    (any BCP-47-ish tag), so adding a language is pure data.
  - Templates interpolate ``{name}`` placeholders.
  - Resolution is total: requested locale -> its base language -> the fallback
    locale (default ``en``) -> its base -> any available -> the key itself. A
    message is never empty, even for an untranslated locale.
"""

from __future__ import annotations

from typing import Mapping

#: BaseLocale is the locale every catalog MUST provide (fallback termination).
BASE_LOCALE = "en"

Params = Mapping[str, object]
Catalog = Mapping[str, Mapping[str, str]]


def base_lang(locale: str) -> str:
    """Lowercase and strip the region/script subtag: ``zh-CN``, ``zh_Hans`` and
    ``ZH`` all collapse to ``zh``."""
    l = locale.strip().lower().replace("_", "-")
    i = l.find("-")
    return l[:i] if i >= 0 else l


def _is_ident(s: str) -> bool:
    if s == "":
        return False
    return all(c == "_" or c.isascii() and (c.isalnum()) for c in s)


def interpolate(template: str, params: Params | None = None) -> str:
    """Replace ``{name}`` placeholders; an unknown name is left literal."""
    if not params:
        return template
    out: list[str] = []
    i = 0
    while i < len(template):
        c = template[i]
        if c != "{":
            out.append(c)
            i += 1
            continue
        end = template.find("}", i)
        if end < 0:
            out.append(template[i:])
            break
        name = template[i + 1 : end]
        if not _is_ident(name):
            out.append(c)
            i += 1
            continue
        if name in params:
            out.append(str(params[name]))
        else:
            out.append("{" + name + "}")
        i = end + 1
    return "".join(out)


def translate(c: Catalog, key: str, locale: str, params: Params | None = None, fallback: str = "") -> str:
    """Resolve one message. ``locale`` may be a full tag; matching walks
    exact -> base(locale) -> fallback -> base(fallback) -> first-available ->
    the key itself."""
    entry = c.get(key)
    if not entry:
        return key
    fb = fallback or BASE_LOCALE
    for cand in (locale, base_lang(locale), fb, base_lang(fb)):
        tpl = entry.get(cand)
        if tpl is not None:
            return interpolate(tpl, params)
    # Last resort: any available translation, else the key. Try the common
    # locales first for a deterministic pick.
    for cand in (BASE_LOCALE, "zh"):
        tpl = entry.get(cand)
        if tpl is not None:
            return interpolate(tpl, params)
    for tpl in entry.values():
        return interpolate(tpl, params)
    return key


class Translator:
    """A Catalog bound to a fallback locale."""

    def __init__(self, catalog: Catalog, fallback: str = "") -> None:
        self.catalog = catalog
        self.fallback = fallback or BASE_LOCALE

    def t(self, locale: str, key: str, params: Params | None = None) -> str:
        return translate(self.catalog, key, locale, params, self.fallback)


def define_i18n(catalog: Catalog, fallback: str = "") -> Translator:
    """Bind a catalog to a fallback locale (default ``en``)."""
    return Translator(catalog, fallback)


# ---- manifest-side description localization --------------------------------


def resolve_description(description: str, descriptions: Mapping[str, str] | None, locale: str) -> str:
    """Resolve a manifest ``description`` for a locale (``descriptions[locale]``
    -> the base string)."""
    if locale and descriptions and locale in descriptions:
        return descriptions[locale]
    return description


def resolve_schema(node: object, locale: str) -> object:
    """Walk a JSON-Schema node and localize every ``description`` from its
    sibling ``descriptions[locale]``, stripping the ``descriptions`` key (the
    convention shared with the Go/TS SDKs) so the schema reaches a model clean."""
    if isinstance(node, list):
        return [resolve_schema(n, locale) for n in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, object] = {}
    for k, v in node.items():
        if k == "descriptions":
            continue
        if k == "description" and isinstance(v, str):
            descs = node.get("descriptions")
            out["description"] = resolve_description(v, descs if isinstance(descs, dict) else None, locale)
            continue
        out[k] = resolve_schema(v, locale)
    return out
