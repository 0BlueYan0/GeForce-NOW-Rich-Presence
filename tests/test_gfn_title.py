import unittest

from src.core.gfn_title import (
    GFN_GAMEWALL_TEMPLATES,
    GFN_TITLE_TEMPLATES,
    STEAM_LANG_BY_LOCALE,
    is_junk_game_name,
    parse_gfn_window_title,
)

# Spread of shapes the parser has to survive: Latin, Latin with punctuation and
# digits, and the CJK names GFN actually serves to a zh-TW client.
SAMPLE_GAMES = [
    "Wuthering Waves",
    "Lost Ark",
    "DOOM: The Dark Ages",
    "光與影：33號遠征隊",
    "幻塔",
]


class TestTemplateRoundTrip(unittest.TestCase):
    """Render every official template, then parse it back."""

    def test_every_locale_round_trips(self):
        failures = []
        for table_name, table in (("interface.gametitle", GFN_TITLE_TEMPLATES),
                                  ("iosGameWall.pageTitle", GFN_GAMEWALL_TEMPLATES)):
            for locale, template in table.items():
                for game in SAMPLE_GAMES:
                    title = template.replace("{title}", game)
                    parsed, _locale = parse_gfn_window_title(title)
                    if parsed != game:
                        failures.append(
                            "%s/%s: %r -> %r (expected %r)" % (table_name, locale, title, parsed, game)
                        )
        self.assertEqual([], failures, "\n".join(failures))

    def test_locale_is_reported(self):
        self.assertEqual(("Wuthering Waves", "zh_TW"),
                         parse_gfn_window_title("在 GeForce NOW 上玩 Wuthering Waves"))
        self.assertEqual("es_ES",
                         parse_gfn_window_title("Wuthering Waves en GeForce NOW")[1])

    def test_every_localising_locale_has_a_template(self):
        # A Steam language mapping is useless without a template to detect it.
        self.assertEqual(set(), set(STEAM_LANG_BY_LOCALE) - set(GFN_TITLE_TEMPLATES))


class TestRealWorldTitles(unittest.TestCase):
    """Titles captured verbatim from a zh-TW GFN client's own history."""

    def test_regression_traditional_chinese(self):
        # The reported bug: this used to parse to the single character 在.
        self.assertEqual("Wuthering Waves",
                         parse_gfn_window_title("在 GeForce NOW 上玩 Wuthering Waves")[0])

    def test_regression_traditional_chinese_localised_names(self):
        self.assertEqual("光與影：33號遠征隊",
                         parse_gfn_window_title("在 GeForce NOW 上玩 光與影：33號遠征隊")[0])
        self.assertEqual("燕雲十六聲",
                         parse_gfn_window_title("在 GeForce NOW 上玩 燕雲十六聲")[0])

    def test_spanish_client(self):
        # From windows_list.txt, captured on a Spanish client.
        self.assertEqual("Forza Horizon 6",
                         parse_gfn_window_title("Forza Horizon 6 en GeForce NOW")[0])


class TestAmbiguousLocales(unittest.TestCase):
    """Templates that overlap and must be disambiguated by specificity."""

    def test_simplified_chinese_not_claimed_by_korean(self):
        # ko_KR is "GeForce NOW {title}", which would otherwise match and yield
        # "上的 幻塔".
        self.assertEqual(("幻塔", "zh_CN"), parse_gfn_window_title("GeForce NOW 上的 幻塔"))

    def test_korean_still_matches(self):
        self.assertEqual(("Lost Ark", "ko_KR"), parse_gfn_window_title("GeForce NOW Lost Ark"))

    def test_gamewall_beats_bare_template(self):
        self.assertEqual("Wuthering Waves",
                         parse_gfn_window_title("Play Wuthering Waves on GeForce NOW")[0])
        self.assertEqual("Rust", parse_gfn_window_title("Juegue a Rust en GeForce NOW")[0])


class TestNonGameTitles(unittest.TestCase):
    def test_lobby_title_yields_no_game(self):
        # find_active_game treats "" as "no game" and falls back to lobby state.
        self.assertEqual("", parse_gfn_window_title("GeForce NOW")[0])

    def test_empty_and_none(self):
        self.assertEqual(("", None), parse_gfn_window_title(""))
        self.assertEqual(("", None), parse_gfn_window_title("   "))

    def test_bare_name_passes_through(self):
        # macOS reads DRSAppName straight out of the GFN log: no brand present.
        self.assertEqual("Wuthering Waves", parse_gfn_window_title("Wuthering Waves")[0])

    def test_browser_suffix_is_not_a_game(self):
        self.assertEqual("", parse_gfn_window_title("GeForce NOW - Google Chrome")[0])

    def test_trademark_glyphs_are_dropped(self):
        self.assertEqual("Wuthering Waves",
                         parse_gfn_window_title("Wuthering Waves™ on GeForce NOW")[0])

    def test_non_breaking_and_ideographic_spaces(self):
        self.assertEqual("Wuthering Waves",
                         parse_gfn_window_title("在　GeForce NOW 上玩 Wuthering Waves")[0])

    def test_unknown_brand_first_layout_degrades_gracefully(self):
        # A brand-first layout we have no template for is indistinguishable from
        # Korean ("GeForce NOW {title}"), so it is reported as ko_KR.  What
        # matters is that the game name survives instead of collapsing to "".
        parsed, _locale = parse_gfn_window_title("GeForce NOW xyzzy Wuthering Waves")
        self.assertIn("Wuthering Waves", parsed)

    def test_unknown_suffix_layout_degrades_gracefully(self):
        # No template matches, so the heuristic has to keep the game-bearing side.
        parsed, locale = parse_gfn_window_title("Wuthering Waves xyzzy GeForce NOW")
        self.assertEqual("Wuthering Waves xyzzy", parsed)
        self.assertIsNone(locale)


class TestIsJunkGameName(unittest.TestCase):
    def test_rejects_mis_parses(self):
        for junk in ["", "   ", "在", "on", "EN", "上玩", "GeForce NOW", "の"]:
            self.assertTrue(is_junk_game_name(junk), junk)

    def test_keeps_real_short_games(self):
        # These are genuine keys in config/games_config_merged.json.
        for real in ["Hob", "Fe", "C9", "Ib", "幻塔", "雀姬", "N++", "osu!"]:
            self.assertFalse(is_junk_game_name(real), real)


if __name__ == "__main__":
    unittest.main()
