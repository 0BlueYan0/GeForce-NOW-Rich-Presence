import unittest
from unittest.mock import patch, MagicMock

from src.core.steam_scraper import (
    get_steam_now_playing,
    SteamStatusUnavailable,
    parse_profile_in_game,
    resolve_steam_id64,
)

# In-game block trimmed from the live steamcommunity.com/id/0BlueYan0/ page (2026-10-07).
IN_GAME_HTML = (
    '<div class="profile_in_game persona in-game">\n\t<div class="profile_in_game_header">Currently In-Game</div>\n'
    '\t<div class="profile_in_game_name">\n\t\tFINAL FANTASY VII REMAKE INTERGRADE\n\t</div>\n'
    '\t<div class="profile_in_game_joingame"></div>\n</div>'
)
# Not captured live; built from the same markup with the online state.
ONLINE_HTML = (
    '<div class="profile_in_game persona online">\n\t<div class="profile_in_game_header">Currently Online</div>\n</div>'
    '<div class="profile_in_game_name">Should not be read</div>'
)
PROFILE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><profile>\n'
    '\t<steamID64>76561198308179097</steamID64>\n\t<onlineState>in-game</onlineState>\n</profile>'
)


def _resp(text, status=200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.history = []
    return r


class ParseProfileInGameTests(unittest.TestCase):
    def test_in_game(self):
        self.assertEqual(parse_profile_in_game(IN_GAME_HTML), "FINAL FANTASY VII REMAKE INTERGRADE")

    def test_online_not_in_game(self):
        self.assertIsNone(parse_profile_in_game(ONLINE_HTML))

    def test_private_profile_has_no_block(self):
        self.assertIsNone(parse_profile_in_game("<div class=\"profile_private_info\">This profile is private.</div>"))

    def test_html_entities_in_name(self):
        html = IN_GAME_HTML.replace("FINAL FANTASY VII REMAKE INTERGRADE", "Tom Clancy&#39;s The Division")
        self.assertEqual(parse_profile_in_game(html), "Tom Clancy's The Division")


class GetSteamNowPlayingTests(unittest.TestCase):
    @patch("src.core.steam_scraper.requests.get")
    def test_reads_profile_page(self, mock_get):
        mock_get.return_value = _resp(IN_GAME_HTML)
        result = get_steam_now_playing("76561198308179097")
        self.assertEqual(result, {"name": "FINAL FANTASY VII REMAKE INTERGRADE", "steam_appid": None})
        self.assertTrue(mock_get.call_args[0][0].endswith("/profiles/76561198308179097/"))

    @patch("src.core.steam_scraper.requests.get")
    def test_invalid_id_makes_no_request(self, mock_get):
        self.assertIsNone(get_steam_now_playing("abc"))
        mock_get.assert_not_called()

    @patch("src.core.steam_scraper.requests.get")
    def test_rate_limit_is_not_reported_as_not_playing(self, mock_get):
        mock_get.return_value = _resp("<title>Steam Community :: Error</title>", status=429)
        with self.assertRaises(SteamStatusUnavailable) as ctx:
            get_steam_now_playing("76561198308179097")
        self.assertTrue(ctx.exception.rate_limited)

    @patch.dict("src.core.steam_scraper._profile_urls", clear=True)
    @patch("src.core.steam_scraper.requests.get")
    def test_remembers_custom_url_redirect(self, mock_get):
        redirected = _resp(IN_GAME_HTML)
        redirected.history = [MagicMock(status_code=302)]
        redirected.url = "https://steamcommunity.com/id/0BlueYan0/"
        mock_get.return_value = redirected
        get_steam_now_playing("76561198308179097")
        get_steam_now_playing("76561198308179097")
        self.assertEqual(mock_get.call_args[0][0], "https://steamcommunity.com/id/0BlueYan0/")


class ResolveSteamId64Tests(unittest.TestCase):
    @patch("src.core.steam_scraper.requests.get")
    def test_numeric_id(self, mock_get):
        self.assertEqual(resolve_steam_id64("76561198308179097"), "76561198308179097")
        mock_get.assert_not_called()

    @patch("src.core.steam_scraper.requests.get")
    def test_profiles_url(self, mock_get):
        url = "https://steamcommunity.com/profiles/76561198308179097/"
        self.assertEqual(resolve_steam_id64(url), "76561198308179097")
        mock_get.assert_not_called()

    @patch("src.core.steam_scraper.requests.get")
    def test_custom_url(self, mock_get):
        mock_get.return_value = _resp(PROFILE_XML)
        self.assertEqual(resolve_steam_id64("https://steamcommunity.com/id/0BlueYan0/"), "76561198308179097")
        self.assertIn("/id/0BlueYan0/?xml=1", mock_get.call_args[0][0])

    @patch("src.core.steam_scraper.requests.get")
    def test_bare_vanity_name(self, mock_get):
        mock_get.return_value = _resp(PROFILE_XML)
        self.assertEqual(resolve_steam_id64("0BlueYan0"), "76561198308179097")

    @patch("src.core.steam_scraper.requests.get")
    def test_unknown_profile(self, mock_get):
        mock_get.return_value = _resp("<response><error>The specified profile could not be found.</error></response>")
        self.assertIsNone(resolve_steam_id64("no-such-user-xyz"))

    def test_empty(self):
        self.assertIsNone(resolve_steam_id64("  "))


if __name__ == "__main__":
    unittest.main()
