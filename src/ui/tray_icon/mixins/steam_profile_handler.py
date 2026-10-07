import os
import logging
from typing import TYPE_CHECKING
from PyQt5.QtWidgets import QSystemTrayIcon

from src.ui.dialogs import GamingMessageBox, GamingTextInputDialog
from src.core.steam_scraper import resolve_steam_id64
from src.core.utils import get_lang_from_registry, load_locale

try:
    LANG = get_lang_from_registry()
    TEXTS = load_locale(LANG)
except Exception:
    LANG = os.getenv('GEFORCE_LANG', 'en')
    TEXTS = load_locale(LANG)

logger = logging.getLogger('geforce_presence')

if TYPE_CHECKING:
    from ..tray_icon import SystemTrayIcon
    Base = SystemTrayIcon
else:
    Base = object

class SteamProfileHandlerMixin(Base):
    """
    Mixin para configurar el perfil público de Steam usado como fuente alternativa del juego activo.
    """
    def configure_steam_profile(self):
        current = self.config_manager.get_setting("steam_profile", "")

        value, ok = GamingTextInputDialog.get_text(
            None,
            TEXTS.get("steam_profile_title", "Steam profile"),
            TEXTS.get("steam_profile_label", "Steam profile URL or SteamID64 (profile must be public):"),
            current
        )
        if not ok:
            return

        value = value.strip()
        if not value:
            self.config_manager.set_setting("steam_profile", "")
            self.config_manager.set_setting("steam_id64", "")
            self.pm._steam_status_cache = (0, None)
            logger.info("Perfil de Steam eliminado de la configuración.")
            return

        try:
            steam_id64 = resolve_steam_id64(value)
        except Exception as e:
            logger.warning(f"No se pudo consultar el perfil de Steam: {e}")
            steam_id64 = None

        if not steam_id64:
            GamingMessageBox.show_warning(
                None,
                TEXTS.get("steam_profile_title", "Steam profile"),
                TEXTS.get("steam_profile_invalid", "Steam profile not found. Check the URL and try again.")
            )
            return

        self.config_manager.set_setting("steam_profile", value)
        self.config_manager.set_setting("steam_id64", steam_id64)
        self.pm._steam_status_cache = (0, None)
        logger.info(f"✅ Perfil de Steam configurado: {steam_id64}")
        self.showMessage(
            TEXTS.get("steam_profile_title", "Steam profile"),
            TEXTS.get("steam_profile_saved", "Steam profile saved."),
            QSystemTrayIcon.Information,
            3000
        )
