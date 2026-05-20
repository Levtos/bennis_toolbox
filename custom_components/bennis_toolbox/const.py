"""Constants for the bennis_toolbox umbrella integration."""

from __future__ import annotations

DOMAIN = "bennis_toolbox"

# Teilintegrationen, die unter dem Toolbox-Dach observiert werden.
# Eintragsformat: (domain, anzeigename, kurzbeschreibung)
# WICHTIG: bewusst nur Beobachtung, keine harte Abhängigkeit.
KNOWN_MEMBERS: tuple[tuple[str, str, str], ...] = (
    ("wake_planner",         "Wake Planner",         "Weckzeiten- und Routinenplanung"),
    ("title_classifier",     "Title Classifier",     "Entity-Title-Mapping / Klassifikation"),
    ("benni_context",        "Benni Context",        "Allgemeiner Kontext-Service"),
    ("benni_media_context",  "Benni Media Context",  "Medien-/Player-Kontext"),
    ("notification_router",  "Notification Router",  "Routing von Notifications"),
    ("plug_policy_engine",   "Plug Policy Engine",   "Steckdosen-Policies"),
    ("stash_ha",             "Stash HA",             "Stash-Mediaplayer-Bridge"),
    ("maw",                  "Media Art Wrapper",    "Cover-Art-/Metadaten-Wrapper"),
)

# Alte Domains aus Vor-Release-Phase. Nur zur Erkennung evtl. verbliebener
# Test-Config-Entries — nie als Zielnamen. Wenn eine dieser Domains noch im
# System ein Config-Entry hat, gibt der Member-Sensor "legacy" + Hinweis aus.
LEGACY_DOMAINS: dict[str, str] = {
    "etm":                       "title_classifier",
    "benni_notification_router": "notification_router",
    "benni_plug_policy":         "plug_policy_engine",
    "stash_player":              "stash_ha",
    "media_art_wrapper":         "maw",
}

CONF_SHOW_MISSING = "show_missing"
DEFAULT_SHOW_MISSING = True
