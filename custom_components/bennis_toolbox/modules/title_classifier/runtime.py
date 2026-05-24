"""WatcherRuntime — beobachtet eine Quell-Entity und extrahiert Title-Keys."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    ARTIST_ATTRIBUTE_CANDIDATES,
    CONF_ARTIST_ATTRIBUTE,
    CONF_AUTO_HIDE_HOURS,
    CONF_RETENTION_DAYS,
    CONF_SOURCE_ENTITY,
    CONF_WATCHER_TYPE,
    DEFAULT_ARTIST_ATTRIBUTE,
    IGNORED_RAW_VALUES,
    MEDIA_FEATURE_MARKERS,
    MEDIA_RICH_TITLE_MARKERS,
    RADIO_STATION_ATTRIBUTE_CANDIDATES,
    TITLE_ATTRIBUTE_CANDIDATES,
)
from .storage import MapperStore


class WatcherRuntime:
    """Runtime-Zustand für einen Watcher-Config-Entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = MapperStore(hass, entry.entry_id)
        self.current_key: str | None = None
        self.current_enum: int | None = None
        self._remove_listener = None
        self._listeners: list[Callable[[], None]] = []

    @property
    def name(self) -> str:
        return self.entry.data[CONF_NAME]

    @property
    def source_entity(self) -> str:
        return self.entry.data[CONF_SOURCE_ENTITY]

    @property
    def auto_hide_hours(self) -> int:
        raw = self.entry.options.get(CONF_AUTO_HIDE_HOURS)
        if raw is None:
            return 0
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0

    def auto_hide_cutoff(self) -> datetime | None:
        hours = self.auto_hide_hours
        if hours <= 0:
            return None
        return dt_util.utcnow() - timedelta(hours=hours)

    def add_listener(self, update_callback) -> None:
        self._listeners.append(update_callback)

    def remove_listener(self, update_callback) -> None:
        if update_callback in self._listeners:
            self._listeners.remove(update_callback)

    async def async_setup(self) -> None:
        await self.store.async_load()
        self._remove_listener = async_track_state_change_event(
            self.hass, [self.source_entity], self._async_source_changed
        )
        state = self.hass.states.get(self.source_entity)
        if state is not None:
            await self.async_process_state(state)

    async def async_unload(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        self._listeners.clear()

    @callback
    def notify_listeners(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()

    def refresh_current_enum(self) -> None:
        self.current_enum = self.store.get_enum(self.current_key) if self.current_key else None

    def catalog_summary(self) -> dict[str, Any]:
        entries = self.store.sorted_entries()
        return {
            "entry_count": len(entries),
            "known_titles": [entry.key for entry in entries],
            "mapped_titles": {entry.key: entry.enum for entry in entries if entry.enum != 0},
            "unmapped_titles": [entry.key for entry in entries if entry.enum == 0],
        }

    async def async_set_current_enum(self, enum: int) -> None:
        if self.current_key is None:
            raise ServiceValidationError(
                "No current Title Classifier title is available to map"
            )
        await self.store.async_set_enum(self.current_key, enum)
        self.refresh_current_enum()
        self.notify_listeners()

    async def _async_source_changed(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is not None:
            await self.async_process_state(new_state)

    async def async_process_state(self, state: State) -> None:
        key = self.key_from_state(state)
        if not key:
            self._clear_current_title()
            return
        if self.entry.data[CONF_WATCHER_TYPE] == "media":
            key = self._resolve_media_duplicate_key(key)
        await self.store.async_seen(key)
        self.current_key = key
        self.refresh_current_enum()
        self.notify_listeners()

    def _clear_current_title(self) -> None:
        if self.current_key is None and self.current_enum is None:
            return
        self.current_key = None
        self.current_enum = None
        self.notify_listeners()

    def key_from_state(self, state: State) -> str | None:
        if clean_value(state.state) is None:
            return None
        watcher_type = self.entry.data[CONF_WATCHER_TYPE]
        title = self._title_from_attributes(state, watcher_type)
        if title is None and watcher_type != "media":
            title = clean_value(state.state)
        if title is None:
            return None
        artist = self._resolve_artist(state, watcher_type)
        if watcher_type == "media" and artist:
            return f"{artist} - {title}"
        return title

    def _resolve_artist(self, state: State, watcher_type: str) -> str | None:
        """Pull an artist string from the source state's attributes.

        Lookup order:
        1. The user-configured ``CONF_ARTIST_ATTRIBUTE`` (if set).
        2. The generic ``ARTIST_ATTRIBUTE_CANDIDATES`` chain — picks up
           ``media_artist`` (classic media_player), ``artist`` (Music
           Assistant), and the album-artist variants.
        3. For ``media`` watchers only: ``RADIO_STATION_ATTRIBUTE_
           CANDIDATES`` so radio streams without a track-level artist
           still get a meaningful grouping key (the station name acts
           as a synthetic artist).
        """
        configured = self.entry.data.get(CONF_ARTIST_ATTRIBUTE)
        attempts: list[str] = []
        if configured:
            attempts.append(configured)
        for attr in ARTIST_ATTRIBUTE_CANDIDATES:
            if attr not in attempts:
                attempts.append(attr)
        for attr in attempts:
            value = clean_value(state.attributes.get(attr))
            if value:
                return value
        if watcher_type == "media":
            for attr in RADIO_STATION_ATTRIBUTE_CANDIDATES:
                value = clean_value(state.attributes.get(attr))
                if value:
                    return value
        return None

    def _title_from_attributes(self, state: State, watcher_type: str) -> str | None:
        values = [
            value
            for attribute in TITLE_ATTRIBUTE_CANDIDATES[watcher_type]
            if (value := clean_value(state.attributes.get(attribute))) is not None
        ]
        if not values:
            return None
        if watcher_type == "media":
            return max(values, key=media_title_score)
        return values[0]

    def _resolve_media_duplicate_key(self, key: str) -> str:
        duplicate_keys = [
            existing_key
            for existing_key in self.store.entries
            if media_keys_match(existing_key, key)
        ]
        if not duplicate_keys:
            return key
        best_key = max([key, *duplicate_keys], key=media_key_score)
        if best_key == key:
            self.store.merge_keys_in_memory(best_key, duplicate_keys)
        return best_key

    def as_panel_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry.entry_id,
            "name": self.name,
            "source_entity": self.source_entity,
            "watcher_type": self.entry.data[CONF_WATCHER_TYPE],
            "retention_days": self.entry.options.get(CONF_RETENTION_DAYS),
            "current_key": self.current_key,
            "current_enum": self.current_enum,
            **self.catalog_summary(),
            "entries": [item.as_dict() for item in self.store.sorted_entries()],
        }


# --------------------------------------------------------------- pure helpers


def clean_value(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if value.lower() in IGNORED_RAW_VALUES:
        return None
    return value


def split_media_key(key: str) -> tuple[str, str]:
    if " - " not in key:
        return "", key
    artist, title = key.split(" - ", 1)
    return artist, title


def normalise_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def normalise_artist(value: str) -> str:
    value = re.split(
        r"\s+(?:feat\.?|ft\.?|featuring)\s+|\s*&\s*|,",
        value, maxsplit=1, flags=re.I,
    )[0]
    return normalise_text(value)


def normalise_title(value: str) -> str:
    value = re.sub(r"\([^)]*\)", "", value)
    return normalise_text(value)


def media_keys_match(left: str, right: str) -> bool:
    left_artist, left_title = split_media_key(left)
    right_artist, right_title = split_media_key(right)
    return (
        normalise_artist(left_artist) == normalise_artist(right_artist)
        and normalise_title(left_title) == normalise_title(right_title)
    )


def media_title_score(title: str) -> int:
    lowered = title.lower()
    marker_score = 20 if any(marker in lowered for marker in MEDIA_RICH_TITLE_MARKERS) else 0
    detail_score = 10 if "(" in title and ")" in title else 0
    return marker_score + detail_score + len(title)


def media_artist_score(artist: str) -> int:
    lowered = artist.lower()
    marker_score = 10 if any(marker in lowered for marker in MEDIA_FEATURE_MARKERS) else 0
    return marker_score + len(artist)


def media_key_score(key: str) -> int:
    artist, title = split_media_key(key)
    return media_title_score(title) + media_artist_score(artist)


def normalise_user_key(key: str) -> str:
    """Normalise a manually supplied title/key."""
    key = str(key).strip()
    if not key:
        raise ServiceValidationError(
            "Title Classifier key/title must not be empty"
        )
    return key
