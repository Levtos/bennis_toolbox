"""Two coordinators für Stash HA: Library-Statistik + Playback-Erkennung."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from ...const import DATA_ENTRIES, DOMAIN
from .client import StashClient
from .const import (
    ACTIVE_SCENE_QUERY,
    DEFAULT_LIBRARY_SCAN_INTERVAL,
    MODULE_ID,
)
from .playback_logic import (
    evaluate_scene_signal,
    parse_play_duration,
    prune_stale_signals,
    rewrite_url,
    summarise_last_played,
)

_LOGGER = logging.getLogger(__name__)


class StashLibraryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls library statistics every 5 minutes."""

    def __init__(self, hass: HomeAssistant, client: StashClient, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{MODULE_ID}_lib_{entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_LIBRARY_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return {
                "scenes":     await self.client.get_scenes_count(),
                "movies":     await self.client.get_movies_count(),
                "performers": await self.client.get_performers_count(),
                "studios":    await self.client.get_studios_count(),
                "tags":       await self.client.get_tags_count(),
                "images":     await self.client.get_images_count(),
                "galleries":  await self.client.get_galleries_count(),
                "markers":    await self.client.get_markers_count(),
                "version":    await self.client.get_version(),
            }
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Library update failed: {err}") from err


class StashPlaybackCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls Stash for active playback via play_duration deltas.

    See ``playback_logic`` for the detection rules.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: StashClient,
        entry: ConfigEntry,
        poll_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{MODULE_ID}_pb_{entry.entry_id}",
            update_interval=timedelta(seconds=max(2, poll_interval)),
        )
        self.client = client
        # scene_id -> {"play_duration": float, "last_activity_ts": float}
        self._scene_signals: dict[str, dict[str, Any]] = {}

    def _fix_paths(self, scene: dict) -> dict:
        paths = scene.get("paths") or {}
        screenshot = paths.get("screenshot")
        if screenshot:
            paths["screenshot"] = rewrite_url(self.client.stash_url, screenshot)
            scene["paths"] = paths
        return scene

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            raw = await self.client._post_allow_errors(ACTIVE_SCENE_QUERY)
            scenes_raw = (
                ((raw.get("data") or {}).get("findScenes") or {}).get("scenes") or []
            )
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Playback update failed: {err}") from err

        now = dt_util.utcnow()
        now_ts = now.timestamp()

        streaming_scenes: list[dict] = []
        active_scene_ids: set[str] = set()
        seen_ids: set[str] = set()

        for raw_scene in scenes_raw:
            sid_val = raw_scene.get("id")
            if sid_val is None:
                continue
            sid = str(sid_val)
            seen_ids.add(sid)

            scene = self._fix_paths(dict(raw_scene))
            play_duration = parse_play_duration(scene.get("play_duration"))

            last_played_age_s: float | None = None
            lpa = scene.get("last_played_at")
            if lpa:
                lp_dt = dt_util.parse_datetime(lpa)
                if lp_dt is not None:
                    last_played_age_s = (now - lp_dt).total_seconds()

            result = evaluate_scene_signal(
                play_duration=play_duration,
                prev_signal=self._scene_signals.get(sid),
                last_played_age_s=last_played_age_s,
                now_ts=now_ts,
            )
            self._scene_signals[sid] = {
                "play_duration": result["play_duration"],
                "last_activity_ts": result["last_activity_ts"],
            }

            if result["streaming"]:
                scene["_is_streaming"] = True
                streaming_scenes.append(scene)
                active_scene_ids.add(sid)

        prune_stale_signals(self._scene_signals, seen_ids, now_ts)

        last_played_summary: dict | None = None
        if scenes_raw:
            top = self._fix_paths(dict(scenes_raw[0]))
            last_played_summary = summarise_last_played(top)

        return {
            "scenes": streaming_scenes,
            "is_streaming": bool(active_scene_ids),
            "active_scene_ids": active_scene_ids,
            "active_stream_count": len(active_scene_ids),
            "last_played": last_played_summary,
        }


# ------------------------------------------------------------------- lookups


def runtime_from_hass(hass: HomeAssistant, entry_id: str) -> dict[str, Any] | None:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry_id)
    if not bucket:
        return None
    return bucket.get("runtime")


def all_stash_runtimes(hass: HomeAssistant) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bucket in hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).values():
        if bucket.get("module_id") != MODULE_ID:
            continue
        rt = bucket.get("runtime")
        if rt is not None:
            out.append(rt)
    return out
