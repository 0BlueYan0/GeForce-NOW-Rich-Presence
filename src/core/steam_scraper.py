import requests
import logging
import re
from html import unescape
from typing import Optional, Tuple
from urllib.parse import quote

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

logger = logging.getLogger('geforce_presence')

class SteamScraper: 
    def __init__(self, steam_cookie: Optional[str], test_rich_url: str):
        self.test_rich_url = test_rich_url
        self.session = requests.Session()
        if steam_cookie:
            self.session.cookies.set('steamLoginSecure', steam_cookie, domain='steamcommunity.com')
        
        # Headers básicos para parecer un navegador
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        self._last_presence = None
        self._last_group_size = None
        
    def set_cookie(self, steam_cookie: str):
        if steam_cookie:
            self.session.cookies.set('steamLoginSecure', steam_cookie, domain='steamcommunity.com')
            self._steam_expired_warned = False
            logger.info("🍪 Cookie de Steam actualizada en el Scraper.")


    def get_rich_presence(self) -> Tuple[Optional[str], Optional[int]]:
        """
        Retorna una tupla (rich_presence_text, group_size)
        """
        if not self.test_rich_url:
            logger.debug("No TEST_RICH_URL configurada.")
            return None, None
        
        try:
            resp = self.session.get(self.test_rich_url, timeout=10)
            if resp.status_code != 200:
                logger.debug("Status != 200 al obtener rich presence")
                return None, None
            
            if "Sign In" in resp.text or "login" in resp.url.lower():
                if not getattr(self, "_steam_expired_warned", False):
                    logger.warning("🔒 Sesión de Steam expirada.")
                    self._steam_expired_warned = True
                return None, None
            else:
                if getattr(self, "_steam_expired_warned", False):
                    logger.info("✅ Sesión de Steam restaurada.")
                    self._steam_expired_warned = False

            rich_presence_text = None
            group_size = None

            if BeautifulSoup is not None:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # 1. Obtener el texto de Rich Presence
                # Intentar primero con "Localized Rich Presence Result"
                b = soup.find('b', string=re.compile(r'Localized Rich Presence Result', re.IGNORECASE))
                if b:
                    text = (b.next_sibling or "").strip()
                    if text and '#' not in text and "No rich presence keys set" not in text:
                        rich_presence_text = text

                # Si falla, intentar buscar "status" en la tabla (fallback mas robusto)
                if not rich_presence_text:
                    rows = soup.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            key = cells[0].get_text().strip().lower()
                            if key == 'status':
                                val = cells[1].get_text().strip()
                                if val and '#' not in val:
                                    rich_presence_text = val
                                    logger.debug(f"✅ Rich Presence encontrado via fallback 'status': {val}")
                                    break
                
                # 2. Extraer steam_player_group_size
                group_size = self._extract_group_size(soup)
            else:
                # Fallback con Regex si bs4 no está disponible
                m = re.search(r'Localized Rich Presence Result.*?</b>\s*([^<\r\n]+)', resp.text, re.IGNORECASE)
                if m:
                    text = m.group(1).strip()
                    if text and '#' not in text and "No rich presence keys set" not in text:
                        rich_presence_text = text
                if not rich_presence_text:
                    m2 = re.search(r'<td[^>]*>\s*status\s*</td>\s*<td[^>]*>\s*([^<\r\n]+)\s*</td>', resp.text, re.IGNORECASE)
                    if m2:
                        rich_presence_text = m2.group(1).strip()
                
                m_grp = re.search(r'<td[^>]*>\s*steam_player_group_size\s*</td>\s*<td[^>]*>\s*(\d+)\s*</td>', resp.text, re.IGNORECASE)
                if m_grp:
                    try:
                        group_size = int(m_grp.group(1))
                    except ValueError:
                        pass
            
            if rich_presence_text:
                if rich_presence_text != self._last_presence:
                    self._last_presence = rich_presence_text
                    logger.info(f"🎮 Rich Presence (nuevo): {rich_presence_text}")
            
            return rich_presence_text, group_size
            
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            raise e
        except Exception as e:
            logger.error(f"⚠️ Error scraping Steam: {e}")
            return None, None
    
    def _extract_group_size(self, soup) -> Optional[int]:
        """
        Extrae el valor de steam_player_group_size de la tabla HTML
        """
        group_size = None
        try:
            # Buscar la fila que contiene 'steam_player_group_size'
            rows = soup.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    first_cell_text = cells[0].get_text().strip()
                    if 'steam_player_group_size' in first_cell_text:
                        # El valor está en la segunda celda
                        group_size_text = cells[1].get_text().strip()
                        if group_size_text.isdigit():
                            group_size = int(group_size_text)
                            if group_size != self._last_group_size:
                                self._last_group_size = group_size
                                logger.info(f"👥 Group size detectado: {group_size}")
                            return group_size
            
            # Si no se encuentra steam_player_group_size, buscar patrones alternativos
            #group_size = self._find_alternative_group_size(soup)
            return group_size
            
        except Exception as e:
            logger.debug(f"Error extrayendo group size: {e}")
            return None
    
    def _find_alternative_group_size(self, soup) -> Optional[int]:
        """
        Busca el group size usando métodos alternativos (XPath simulation)
        """
        try:
            # Método 1: Buscar en todas las celdas que puedan contener números de grupo
            cells = soup.find_all('td')
            for cell in cells:
                text = cell.get_text().strip()
                # Buscar patrones como "1/4", "2 players", etc.
                if '/' in text and text.replace('/', '').isdigit():
                    parts = text.split('/')
                    if len(parts) == 2 and parts[0].isdigit():
                        current_players = int(parts[0])
                        logger.info(f"👥 Group size alternativo detectado: {current_players}")
                        return current_players
            
            # Método 2: Buscar números que representen cantidad de jugadores
            for cell in cells:
                text = cell.get_text().strip()
                if text.isdigit():
                    num = int(text)
                    if 1 <= num <= 16:  # Rango razonable para grupos de juego
                        logger.info(f"👥 Group size numérico detectado: {num}")
                        return num
            
            return None
        except Exception as e:
            logger.debug(f"Error en búsqueda alternativa de group size: {e}")
            return None
            
def find_steam_appid_by_name(game_name: str) -> Optional[str]:
    try:
        url = f"https://steamcommunity.com/actions/SearchApps/{quote(game_name)}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list):
                for app in data:
                    if app.get("name", "").lower() == game_name.lower():
                        return str(app.get("appid"))
                if data:    
                    return str(data[0].get("appid"))
    except Exception as e:
        logger.error(f"Error buscando Steam AppID: {e}")
    return None


STEAM_ID64_BASE = 76561197960265728
_BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}


def resolve_steam_id64(profile: str) -> Optional[str]:
    """Turn a profile URL, custom URL name or SteamID64 into a SteamID64.

    The public ``?xml=1`` profile page answers without a Web API key, which is
    what lets users without a key point the app at their own account.
    """
    text = (profile or "").strip().rstrip("/")
    if not text:
        return None
    m = re.search(r'steamcommunity\.com/(id|profiles)/([^/?#]+)', text)
    if m:
        kind, value = m.group(1), m.group(2)
    else:
        kind, value = ("profiles" if re.fullmatch(r'\d{17}', text) else "id"), text
    if kind == "profiles" and re.fullmatch(r'\d{17}', value):
        return value
    try:
        resp = requests.get(f"https://steamcommunity.com/id/{quote(value)}/?xml=1",
                            headers=_BROWSER_HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        m_id = re.search(r'<steamID64>(\d{17})</steamID64>', resp.text)
        return m_id.group(1) if m_id else None
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        raise
    except Exception as e:
        logger.debug(f"Error resolviendo SteamID64 de '{profile}': {e}")
    return None


def parse_miniprofile_game(html: str) -> Optional[dict]:
    """Read the in-game app from a steamcommunity.com miniprofile.

    The miniprofile is used instead of the ``?xml=1`` page because the XML only
    carries the game name, while the miniprofile's capsule image URL also holds
    the appid.
    """
    if not html or "miniprofile_gamesection" not in html:
        return None
    m_name = re.search(r'class="miniprofile_game_name"[^>]*>([^<]+)<', html)
    if not m_name:
        return None
    name = unescape(m_name.group(1)).strip()
    if not name:
        return None
    m_app = re.search(r'class="game_logo"[^>]*src="[^"]*/apps/(\d+)/', html)
    return {"name": name, "steam_appid": m_app.group(1) if m_app else None}


def get_steam_now_playing(steam_id64: str) -> Optional[dict]:
    """Return ``{"name", "steam_appid"}`` for the game the account is in, else None.

    Only works when the profile and its game details are public.
    """
    try:
        account_id = int(steam_id64) - STEAM_ID64_BASE
    except (TypeError, ValueError):
        return None
    if account_id <= 0:
        return None
    try:
        resp = requests.get(f"https://steamcommunity.com/miniprofile/{account_id}",
                            headers=_BROWSER_HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        return parse_miniprofile_game(resp.text)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        raise
    except Exception as e:
        logger.debug(f"Error leyendo el estado de Steam de {steam_id64}: {e}")
    return None


def resolve_english_name_via_steam(localized_name: str, steam_lang: str,
                                   country: str = "US") -> Optional[Tuple[str, str]]:
    """Map a localised game name back to its English name via the Steam store.

    The GeForce NOW client localises game titles, not just its own UI: a zh-TW
    client reports "光與影：33號遠征隊", while games_config_merged.json is keyed on
    "Clair Obscur: Expedition 33".  Searching the store in the same language the
    title came in, then reading the app back in English, bridges the two.

    Note this deliberately uses store.steampowered.com rather than the
    steamcommunity.com endpoint above -- the latter returns an empty list for
    non-Latin queries.

    Returns ``(english_name, steam_appid)``, or ``None`` if nothing matched.
    """
    if not localized_name or not steam_lang:
        return None
    try:
        resp = requests.get(
            "https://store.steampowered.com/api/storesearch/",
            params={"term": localized_name, "cc": country, "l": steam_lang},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        items = (resp.json() or {}).get("items") or []
        if not items:
            return None

        # Prefer an exact hit on the localised name; the store also returns
        # soundtracks and deluxe editions, which sort alongside the base game.
        appid = None
        for item in items:
            if str(item.get("name", "")).strip().lower() == localized_name.strip().lower():
                appid = item.get("id")
                break
        if appid is None:
            appid = items[0].get("id")
        if appid is None:
            return None

        detail = requests.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": appid, "l": "english"},
            timeout=10,
        )
        if detail.status_code != 200:
            return None
        english = ((detail.json() or {}).get(str(appid)) or {}).get("data", {}).get("name")
        if not english:
            return None
        return str(english).strip(), str(appid)
    except Exception as e:
        logger.debug(f"Error resolviendo nombre localizado '{localized_name}' via Steam: {e}")
    return None
