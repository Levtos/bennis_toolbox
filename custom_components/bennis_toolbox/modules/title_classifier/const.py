"""Title-Classifier-Modul-Konstanten.

Externe HA-Domäne ist `bennis_toolbox`; sämtliche Namespaces werden vom
Toolbox-Helper aus diesem `MODULE_ID` gebaut.
"""

from __future__ import annotations

MODULE_ID = "title_classifier"
NAME = "Title Classifier"

# Config-Schlüssel
CONF_SOURCE_ENTITY = "source_entity"
CONF_ARTIST_ATTRIBUTE = "artist_attribute"
CONF_WATCHER_TYPE = "watcher_type"
CONF_RETENTION_DAYS = "retention_days"
CONF_AUTO_HIDE_HOURS = "auto_hide_hours"

WATCHER_TYPES = ("game", "media", "activity")
DEFAULT_ARTIST_ATTRIBUTE = "media_artist"

# Resolved in order when looking for a track-level artist. Music Assistant
# exposes the attribute simply as ``artist``; classic media_player
# integrations use ``media_artist``. The configured attribute (see
# ``CONF_ARTIST_ATTRIBUTE``) is always tried first; this list is the
# generic fallback chain.
ARTIST_ATTRIBUTE_CANDIDATES: tuple[str, ...] = (
    "media_artist",
    "artist",
    "media_album_artist",
    "album_artist",
)

# When no track-level artist is reported (typical for radio streams),
# the runtime falls back to a "synthetic artist" derived from the
# station/source attribute so panel grouping still works ("WDR 2 POP
# Die Abendshow…" lands under WDR 2 instead of under "— Kein Künstler —").
RADIO_STATION_ATTRIBUTE_CANDIDATES: tuple[str, ...] = (
    "radio_station_name",
    "media_station",
    "station",
    "channel",
    "media_channel",
)
DEFAULT_ENUM = 0
MIN_ENUM = 0
MAX_ENUM = 9

STORAGE_VERSION = 1

ATTR_KEY = "key"
ATTR_ENUM = "enum"
ATTR_ENTRY_ID = "entry_id"
ATTR_WATCHER_ID = "watcher_id"
ATTR_WATCHER_NAME = "watcher_name"
ATTR_DELETED = "deleted"
ATTR_ENTRIES = "entries"

# Service-Aktionen — registriert als `bennis_toolbox.title_classifier_<action>`.
SERVICE_SET_ENUM = "set_enum"
SERVICE_DELETE_ENTRY = "delete_entry"
SERVICE_CLEAR_OLD = "clear_old"
SERVICE_IMPORT_ENTRIES = "import_entries"
SERVICE_HIDE_UNMAPPED = "hide_unmapped"

PANEL_TITLE = "Title Classifier"
PANEL_ICON = "mdi:tag-multiple"

TITLE_ATTRIBUTE_CANDIDATES = {
    "game": (
        "media_title",
        "title",
        "game_title",
        "game_name",
        "app_title",
        "app_name",
        "activity",
        "activity_name",
    ),
    "media": ("media_title", "title"),
    "activity": ("activity", "activity_name", "media_title", "title", "app_name"),
}
IGNORED_RAW_VALUES = {
    "",
    "unknown",
    "unavailable",
    "none",
    "off",
    "idle",
    "standby",
}
MEDIA_RICH_TITLE_MARKERS = ("remix", "mix", "edit", "version", "club", "vip", "bootleg")
MEDIA_FEATURE_MARKERS = (" feat", " ft", " featuring", " & ", ",")
