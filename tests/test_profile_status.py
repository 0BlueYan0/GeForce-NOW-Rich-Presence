import unittest
from unittest.mock import patch, MagicMock

from src.core.steam_scraper import (
    get_steam_now_playing,
    parse_miniprofile_game,
    resolve_steam_id64,
)

# Trimmed from live steamcommunity.com/miniprofile responses (2026-10-07).
IN_GAME_HTML = (
    '<div class="miniprofile_container"> <div class="miniprofile_gamesection miniprofile_backdropblur miniprofile_backdrop">'
    ' <img class="game_logo" src="https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1462040/'
    'ec805ec87558eb40c712c7cca4eabc2e83cb57f7/capsule_184x69.jpg?t=1789446715">'
    ' <div class="miniprofile_game_details"> <span class="game_state">In-Game</span>'
    ' <span class="miniprofile_game_name">FINAL FANTASY VII REMAKE INTERGRADE</span> </div> </div> </div>'
)
OFFLINE_HTML = (
    '<div class="miniprofile_container"> <div class="player_content"> <span class="persona offline">Rabscuttle</span>'
    ' <span class="friend_status_offline">Offline</span> </div>'
    ' <div class="miniprofile_detailssection not_in_game miniprofile_backdrop"> </div> </div>'
)
PROFILE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><profile>\n'
    '\t<steamID64>76561198308179097</steamID64>\n\t<onlineState>in-game</onlineState>\n</profile>'
)


def _resp(text, status=200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


class ParseMiniprofileTests(unittest.TestCase):
    def test_in_game(self):
        self.assertEqual(
            parse_miniprofile_game(IN_GAME_HTML),
            {"name": "FINAL FANTASY VII REMAKE INTERGRADE", "steam_appid": "1462040"},
        )

    def test_not_in_game(self):
        self.assertIsNone(parse_miniprofile_game(OFFLINE_HTML))

    def test_html_entities_in_name(self):
        html = IN_GAME_HTML.replace("FINAL FANTASY VII REMAKE INTERGRADE", "Tom Clancy&#39;s The Division")
        self.assertEqual(parse_miniprofile_game(html)["name"], "Tom Clancy's The Division")


class GetSteamNowPlayingTests(unittest.TestCase):
    @patch("src.core.steam_scraper.requests.get")
    def test_uses_account_id(self, mock_get):
        mock_get.return_value = _resp(IN_GAME_HTML)
        result = get_steam_now_playing("76561198308179097")
        self.assertEqual(result["steam_appid"], "1462040")
        self.assertTrue(mock_get.call_args[0][0].endswith("/miniprofile/347913369"))

    @patch("src.core.steam_scraper.requests.get")
    def test_invalid_id_makes_no_request(self, mock_get):
        self.assertIsNone(get_steam_now_playing("abc"))
        mock_get.assert_not_called()


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
