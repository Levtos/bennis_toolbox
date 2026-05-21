"""Konstanten des Stash-HA-Moduls.

Externe HA-Domain ist `bennis_toolbox`. Storage gibt es keinen; Webhook-URL,
Service- und unique_id-Namespaces werden vom Toolbox-Helper aus `MODULE_ID`
gebaut.
"""
from __future__ import annotations

MODULE_ID = "stash_ha"
NAME = "Stash HA"

# --- Config / options ---
CONF_URL = "url"
CONF_API_KEY = "api_key"
CONF_PLAYER_NAME = "player_name"
CONF_POLL_INTERVAL = "poll_interval"
CONF_USE_WEBHOOK = "use_webhook"
CONF_NSFW_MODE = "nsfw_mode"

DEFAULT_PLAYER_NAME = "Stash"
DEFAULT_POLL_INTERVAL = 5            # seconds; >= 2 enforced in coordinator
DEFAULT_LIBRARY_SCAN_INTERVAL = 300  # 5 min
DEFAULT_USE_WEBHOOK = False
DEFAULT_NSFW_MODE = "blur"

# Playback-detection tuning (see docstring of StashPlaybackCoordinator).
STREAM_ACTIVITY_GRACE_SECONDS = 60
FRESH_PLAY_THRESHOLD_SECONDS = 30
ACTIVE_SCENE_WINDOW = 10

NSFW_BLUR = "blur"
NSFW_HIDDEN = "hidden"
NSFW_FULL = "full"
NSFW_MODES = [NSFW_BLUR, NSFW_HIDDEN, NSFW_FULL]

# --- Services (registered as bennis_toolbox.stash_ha_<action>) ---
SERVICE_METADATA_SCAN = "metadata_scan"
SERVICE_METADATA_CLEAN = "metadata_clean"
SERVICE_METADATA_GENERATE = "metadata_generate"
SERVICE_METADATA_AUTO_TAG = "metadata_auto_tag"
SERVICE_METADATA_IDENTIFY = "metadata_identify"
SERVICE_GENERATE_SCREENSHOT = "generate_screenshot"
SERVICE_SAVE_ACTIVITY = "save_activity"

# --- Entity unique-id suffixes ---
# Library sensors
UID_SCENES = "scenes_count"
UID_MOVIES = "movies_count"
UID_PERFORMERS = "performers_count"
UID_STUDIOS = "studios_count"
UID_TAGS = "tags_count"
UID_IMAGES = "images_count"
UID_GALLERIES = "galleries_count"
UID_MARKERS = "markers_count"
UID_VERSION = "version"
# Playback sensors
UID_ACTIVE_STREAMS = "active_streams"
UID_CURRENTLY_PLAYING = "currently_playing"
UID_LAST_PLAYED_TITLE = "last_played_title"
UID_LAST_PLAYED_AT = "last_played_at"
# Image + media_player
UID_COVER = "cover"
UID_PLAYER = "player"

# --- GraphQL queries -----------------------------------------------------------

ACTIVE_SCENE_QUERY = """
query ActiveScene {
  findScenes(
    scene_filter: { last_played_at: { modifier: NOT_NULL, value: "" } }
    filter: { per_page: 10, sort: "last_played_at", direction: DESC }
  ) {
    scenes {
      id
      title
      rating100
      play_count
      play_duration
      resume_time
      last_played_at
      paths { screenshot }
      performers { name }
      tags { name }
      studio { name }
      files { duration size width height }
    }
  }
}
"""
