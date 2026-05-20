"""Constants for Entity Title Mapper."""

from __future__ import annotations

DOMAIN = "title_classifier"
PLATFORMS = ["sensor", "number"]

CONF_SOURCE_ENTITY = "source_entity"
CONF_ARTIST_ATTRIBUTE = "artist_attribute"
CONF_WATCHER_TYPE = "watcher_type"
CONF_RETENTION_DAYS = "retention_days"
CONF_AUTO_HIDE_HOURS = "auto_hide_hours"

WATCHER_TYPES = ["game", "media", "activity"]
DEFAULT_ARTIST_ATTRIBUTE = "media_artist"
DEFAULT_ENUM = 0
MIN_ENUM = 0
MAX_ENUM = 9

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "title_classifier_"

ATTR_KEY = "key"
ATTR_ENUM = "enum"
ATTR_ENTRY_ID = "entry_id"
ATTR_WATCHER_ID = "watcher_id"
ATTR_WATCHER_NAME = "watcher_name"
ATTR_DELETED = "deleted"
ATTR_ENTRIES = "entries"

SERVICE_SET_ENUM = "set_enum"
SERVICE_DELETE_ENTRY = "delete_entry"
SERVICE_CLEAR_OLD = "clear_old"
SERVICE_IMPORT_ENTRIES = "import_entries"
SERVICE_HIDE_UNMAPPED = "hide_unmapped"

PANEL_URL = "/title_classifier_panel.js"
PANEL_TITLE = "Title Classifier"
PANEL_ICON = "mdi:tag-multiple"
