"""Parsing of the GeForce NOW client window title into a game name.

The GFN window title is rendered from a per-language template, and its shape is
not uniform.  Most European languages put the game first ("<game> on GeForce
NOW"), but zh-TW/zh-CN/ja/ko/tr put the brand first -- the Traditional Chinese
client renders "在 GeForce NOW 上玩 Wuthering Waves".  A regex that deletes
everything from "GeForce NOW" onward therefore returns "在" for those locales
instead of the game name.

The tables below are not guesses: they are lifted verbatim from the GFN client's
own i18n bundles (keys ``interface.gametitle`` and ``iosGameWall.pageTitle``).
Regenerate them when NVIDIA ships new languages:

    import json, glob, os
    I = os.path.join(os.environ['LOCALAPPDATA'], 'NVIDIA Corporation',
                     'GeForceNOW', 'mall', 'assets', 'i18n')
    for f in sorted(glob.glob(os.path.join(I, '*.json'))):
        if os.path.basename(f).startswith('i18n_hashes'):
            continue
        d = json.load(open(f, encoding='utf-8'))
        print(os.path.basename(f).split('.')[0],
              json.dumps((d.get('interface') or {}).get('gametitle'), ensure_ascii=False))

This module imports nothing but the standard library so it stays cheap to unit
test without pulling in PyQt/psutil.
"""

import re
from typing import List, Optional, Tuple

#: GFN desktop window title, per language (key ``interface.gametitle``).
GFN_TITLE_TEMPLATES = {
    "ar_SA": "{title} على GeForce NOW",
    "bg_BG": "{title} в GeForce NOW",
    "cs_CZ": "{title} ve službě GeForce NOW",
    "da_DK": "{title} på GeForce NOW",
    "de_DE": "{title} bei GeForce NOW",
    "el_GR": "{title} στο GeForce NOW",
    "en_GB": "{title} on GeForce NOW",
    "en_US": "{title} on GeForce NOW",
    "es_ES": "{title} en GeForce NOW",
    "es_MX": "{title} en GeForce NOW",
    "fi_FI": "{title} GeForce NOWssa",
    "fr_FR": "{title} sur GeForce NOW",
    "hr_HR": "{title} na GeForce NOW",
    "hu_HU": "{title} a GeForce NOW-n",
    "it_IT": "{title} su GeForce NOW",
    "ja_JP": "GeForce NOW の{title}",
    "ko_KR": "GeForce NOW {title}",
    "nb_NO": "{title} på GeForce NOW",
    "nl_NL": "{title} op GeForce NOW",
    "pl_PL": "{title} w usłudze GeForce NOW",
    "pt_BR": "{title} no GeForce NOW",
    "pt_PT": "{title} no GeForce NOW",
    "ro_RO": "{title} pe GeForce NOW",
    "ru_RU": "{title} в GeForce NOW",
    "sk_SK": "{title} v službe GeForce NOW",
    "sl_SI": "{title} na GeForce NOW",
    "sv_SE": "{title} på GeForce NOW",
    "th_TH": "{title} บน GeForce NOW",
    "tr_TR": "GeForce NOW'da {title}",
    "uk_UA": "{title} на сервісі GeForce NOW",
    "zh_CN": "GeForce NOW 上的 {title}",
    "zh_TW": "在 GeForce NOW 上玩 {title}",
}

#: Verbose "Play X on GeForce NOW" phrasing (key ``iosGameWall.pageTitle``).
GFN_GAMEWALL_TEMPLATES = {
    "ar_SA": "العب {title} على GeForce NOW",
    "bg_BG": "Играйте {title} в GeForce NOW",
    "cs_CZ": "Zahrajte si {title} ve službě GeForce NOW",
    "da_DK": "Spil {title} på GeForce NOW",
    "de_DE": "{title} mit GeForce NOW spielen",
    "el_GR": "Παίξτε {title} στο GeForce NOW",
    "en_GB": "Play {title} on GeForce NOW",
    "en_US": "Play {title} on GeForce NOW",
    "es_ES": "Juegue a {title} en GeForce NOW",
    "es_MX": "Ejecute {title} en GeForce NOW",
    "fi_FI": "Pelaa peliä {title} GeForce NOW:ssa",
    "fr_FR": "Jouer à {title} sur GeForce NOW",
    "hr_HR": "Igrajte igru {title} u usluzi GeForce NOW",
    "hu_HU": "Játszd a(z) {title} játékot a GeForce NOW-n",
    "it_IT": "Gioca {title} su GeForce NOW",
    "ja_JP": "GeForce NOW で {title} をプレイ",
    "ko_KR": "GeForce NOW에서 {title} 플레이하기",
    "nb_NO": "Spill {title} på GeForce NOW",
    "nl_NL": "Speel {title} op GeForce NOW",
    "pl_PL": "Zagraj w grę {title} w usłudze GeForce NOW",
    "pt_BR": "Jogue {title} no GeForce NOW",
    "pt_PT": "Jogar {title} no GeForce NOW",
    "ro_RO": "Jucați {title} pe GeForce NOW",
    "ru_RU": "Играйте в {title} в GeForce NOW",
    "sk_SK": "Zahrajte si hru {title} v službe GeForce NOW",
    "sl_SI": "Predvajajte {title} na GeForce NOW",
    "sv_SE": "Spela {title} på GeForce NOW",
    "th_TH": "เล่น {title} บน GeForce NOW",
    "tr_TR": "GeForce NOW ile {title} Oyna",
    "uk_UA": "Грати {title} на GeForce NOW",
    "zh_CN": "在 GeForce NOW 上玩 {title}",
    "zh_TW": "在 GeForce NOW 上玩 {title}",
}


#: Locales where GFN also localises the *game* name, mapped to the matching
#: Steam API language code.  Used to look the English name back up; locales
#: absent from this map keep game names in Latin script, so no lookup is needed.
STEAM_LANG_BY_LOCALE = {
    "ar_SA": "arabic",
    "bg_BG": "bulgarian",
    "el_GR": "greek",
    "ja_JP": "japanese",
    "ko_KR": "koreana",
    "ru_RU": "russian",
    "th_TH": "thai",
    "uk_UA": "ukrainian",
    "zh_CN": "schinese",
    "zh_TW": "tchinese",
}

#: Whole-string tokens that are never a game name.  These are the connector
#: words the templates place next to the brand; seeing one on its own means the
#: title was mis-parsed.  Matched case-insensitively against the *entire* name,
#: never as a substring -- real games are called "Hob", "Fe", "C9", "幻塔".
_CONNECTOR_TOKENS = frozenset([
    "a", "bei", "en", "in", "na", "no", "on", "op", "pe", "su", "sur", "v",
    "ve", "via", "w", "上玩", "上的", "在", "の", "в", "на", "сервісі",
    "geforce now", "geforcenow",
])

#: Trailing junk contributed by a browser window rather than the GFN client.
#: Without this, a browser-hosted title would fall through to the heuristic and
#: be reported as a game called "Google Chrome".
_BROWSER_SUFFIX_RE = re.compile(
    r"\s*[-—–|]\s*"
    r"(?:Google Chrome|Mozilla Firefox|Microsoft\s*Edge|Brave|Opera|Vivaldi|Chromium)"
    r"\s*$",
    re.IGNORECASE,
)

#: The brand itself.  ``\w*`` absorbs agglutinative suffixes such as the Finnish
#: "GeForce NOWssa"; the optional trailing chunk absorbs Turkish "GeForce NOW'da"
#: and Hungarian "GeForce NOW-n".
_BRAND_RE = re.compile(r"GeForce\s*NOW\w*(?:['’-]\w+)?", re.IGNORECASE)

#: Characters safe to shave off either edge of a candidate name.
_EDGE_CHARS = " \t 　-—–|:·,、："

_TRADEMARKS_RE = re.compile(r"[®™]")
_WHITESPACE_RE = re.compile(r"[\s 　]+")


def _normalize(title: str) -> str:
    """Collapse exotic whitespace and drop trademark glyphs."""
    if not title:
        return ""
    text = _TRADEMARKS_RE.sub("", title)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _loose(literal: str) -> str:
    """Escape a template literal, letting any whitespace in it match loosely.

    Split before escaping: ``re.escape`` turns a space into a backslash-space
    pair, so substituting on the escaped string would corrupt the pattern.
    """
    return r"\s+".join(re.escape(part) for part in _WHITESPACE_RE.split(literal.strip()) if part)


def _compile(template: str) -> "re.Pattern":
    """Turn a GFN title template into an anchored regex capturing the game."""
    head, _, tail = template.partition("{title}")
    parts = [r"^\s*"]
    if head.strip():
        parts.append(_loose(head))
        parts.append(r"\s*")
    parts.append(r"(?P<title>.+?)")
    if tail.strip():
        parts.append(r"\s*")
        parts.append(_loose(tail))
    parts.append(r"\s*$")
    return re.compile("".join(parts), re.IGNORECASE | re.UNICODE)


def _build_patterns() -> List[Tuple[str, str, "re.Pattern"]]:
    """Compile every template, most specific first.

    Ordering by literal length is load-bearing: ko_KR's "GeForce NOW {title}"
    would otherwise match a zh_CN title and yield "上的 幻塔".

    Ties are broken towards ``interface.gametitle``, which is what the desktop
    client actually renders.  zh_CN's game-wall phrasing is identical to zh_TW's
    window title, and reporting zh_CN there would send the localised-name lookup
    to Steam in the wrong Chinese.
    """
    seen = set()
    entries = []
    for rank, table in enumerate((GFN_TITLE_TEMPLATES, GFN_GAMEWALL_TEMPLATES)):
        for locale, template in table.items():
            if "{title}" not in template or (locale, template) in seen:
                continue
            seen.add((locale, template))
            entries.append((rank, locale, template))
    entries.sort(key=lambda kv: (-len(kv[2].replace("{title}", "")), kv[0], kv[1]))
    return [(locale, template, _compile(template)) for _rank, locale, template in entries]


_PATTERNS = _build_patterns()


def _strip_edges(text: str) -> str:
    return text.strip(_EDGE_CHARS)


def _is_connector(text: str) -> bool:
    return text.strip(_EDGE_CHARS + ".'’").lower() in _CONNECTOR_TOKENS


def _drop_connector(text: str, from_end: bool) -> str:
    """Remove one leading/trailing connector word from a heuristic candidate."""
    candidate = _strip_edges(text)
    if not candidate:
        return ""
    parts = candidate.split(" ")
    if len(parts) > 1:
        edge = parts[-1] if from_end else parts[0]
        if _is_connector(edge):
            return _strip_edges(" ".join(parts[:-1] if from_end else parts[1:]))
    return candidate


def _heuristic(text: str) -> str:
    """Fallback for titles no template matched (new GFN languages, macOS logs).

    Splits on the brand and keeps the side that actually carries a name, so a
    brand-first layout we have no template for still degrades to the right
    answer instead of an empty string.
    """
    match = _BRAND_RE.search(text)
    if not match:
        return _strip_edges(text)
    left = _drop_connector(text[:match.start()], from_end=True)
    right = _drop_connector(text[match.end():], from_end=False)
    if not left:
        return right
    if not right:
        return left
    return left if len(left) >= len(right) else right


def parse_gfn_window_title(title: str) -> Tuple[str, Optional[str]]:
    """Extract the game name from a GeForce NOW window title.

    Returns ``(game_name, locale)``.  ``locale`` is the GFN language whose
    template matched, or ``None`` when the name came from the fallback
    heuristic.  ``game_name`` is ``""`` when the title carries no game -- the
    lobby title is just "GeForce NOW" -- which callers treat as "no game".

    >>> parse_gfn_window_title("在 GeForce NOW 上玩 Wuthering Waves")
    ('Wuthering Waves', 'zh_TW')
    >>> parse_gfn_window_title("Wuthering Waves en GeForce NOW")[0]
    'Wuthering Waves'
    >>> parse_gfn_window_title("GeForce NOW")
    ('', None)
    """
    text = _normalize(title)
    if not text:
        return "", None
    text = _BROWSER_SUFFIX_RE.sub("", text).strip()

    for locale, _template, pattern in _PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        name = _strip_edges(_normalize(match.group("title")))
        # Guard against reporting a stray connector or a fragment of the brand
        # as though it were a game.
        if name and not _is_connector(name):
            return name, locale

    return _heuristic(text), None


def is_junk_game_name(name: str) -> bool:
    """True when a parsed name is too degenerate to persist to the game config.

    Guards the auto-add path in ``PresenceManager.find_active_game``: a bad
    parse used to be written to ``games_config_merged.json`` permanently.
    Deliberately conservative -- the shipped config contains real two-character
    games ("Ib", "Fe", "C9", "幻塔"), so only single characters are rejected on
    length alone.
    """
    if not name:
        return True
    candidate = _strip_edges(name)
    if len(candidate) < 2:
        return True
    return _is_connector(candidate)
