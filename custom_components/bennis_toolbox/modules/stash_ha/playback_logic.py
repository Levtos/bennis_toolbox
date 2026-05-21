"""Pure helpers for Stash playback detection.

Stash exposes no first-class "currently streaming" query. We poll the
recently-played scenes and infer activity from `play_duration` deltas. This
module isolates the reasoning so it can be unit-tested without HA / aiohttp.

Detection rule per scene:
  1. Primary — if `play_duration` strictly increased since the last poll, the
     scene is streaming *now*. We treat it as streaming for
     STREAM_ACTIVITY_GRACE_SECONDS after the last observed increase so
     variable save intervals do not flap state.
  2. Fallback for first observation (e.g. HA restart mid-stream) — if there
     is no prior signal for this scene but its `last_played_at` is younger
     than FRESH_PLAY_THRESHOLD_SECONDS, treat it as streaming until the next
     poll provides a real delta.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .const import (
    FRESH_PLAY_THRESHOLD_SECONDS,
    STREAM_ACTIVITY_GRACE_SECONDS,
)


def rewrite_url(base_url: str, url: str) -> str:
    """Replace scheme/host/port of a Stash-returned URL with our base.

    Stash often returns asset URLs with whatever hostname it sees itself as
    (`localhost`, the Docker service name, an internal IP). Those URLs are
    not reachable from Home Assistant, so we keep the path and query but
    swap the authority for the URL the user actually configured.
    """
    base = urlsplit(base_url)
    target = urlsplit(url)
    if not target.scheme and not target.netloc:
        # Relative path — just prepend the base.
        prefix = base_url
        return f"{prefix}{url if url.startswith('/') else '/' + url}"
    return urlunsplit(
        (base.scheme, base.netloc, target.path, target.query, target.fragment)
    )


def parse_play_duration(raw: Any) -> float:
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def is_streaming(last_activity_ts: float | None, now_ts: float) -> bool:
    if last_activity_ts is None:
        return False
    return (now_ts - last_activity_ts) < STREAM_ACTIVITY_GRACE_SECONDS


def evaluate_scene_signal(
    *,
    play_duration: float,
    prev_signal: dict[str, Any] | None,
    last_played_age_s: float | None,
    now_ts: float,
) -> dict[str, Any]:
    """Decide whether a scene should count as streaming based on the latest
    poll.

    Returns:
        {
            "play_duration": float,
            "last_activity_ts": float | None,
            "delta_advanced": bool,
            "fresh_first_seen": bool,
            "streaming": bool,
        }
    """
    delta_advanced = False
    fresh_first_seen = False

    if prev_signal is None:
        if (
            last_played_age_s is not None
            and 0 <= last_played_age_s < FRESH_PLAY_THRESHOLD_SECONDS
        ):
            fresh_first_seen = True
    else:
        prev_duration = parse_play_duration(prev_signal.get("play_duration"))
        if play_duration > prev_duration:
            delta_advanced = True

    last_activity_ts = (prev_signal or {}).get("last_activity_ts")
    if delta_advanced or fresh_first_seen:
        last_activity_ts = now_ts

    return {
        "play_duration": play_duration,
        "last_activity_ts": last_activity_ts,
        "delta_advanced": delta_advanced,
        "fresh_first_seen": fresh_first_seen,
        "streaming": is_streaming(last_activity_ts, now_ts),
    }


def prune_stale_signals(
    signals: dict[str, dict[str, Any]],
    seen_ids: set[str],
    now_ts: float,
) -> None:
    """Drop signal state for scenes we haven't seen in a while. Mutates."""
    cutoff = STREAM_ACTIVITY_GRACE_SECONDS * 2
    stale = [
        sid for sid, sig in signals.items()
        if sid not in seen_ids
        and (now_ts - (sig.get("last_activity_ts") or 0)) > cutoff
    ]
    for sid in stale:
        signals.pop(sid, None)


def summarise_last_played(top_scene: dict[str, Any]) -> dict[str, Any]:
    """Build the `last_played` summary used by sensors."""
    studio = top_scene.get("studio") or {}
    performers = top_scene.get("performers") or []
    return {
        "id": top_scene.get("id"),
        "title": top_scene.get("title"),
        "last_played_at": top_scene.get("last_played_at"),
        "studio": studio.get("name"),
        "performers": [p.get("name") for p in performers if p.get("name")],
        "screenshot": (top_scene.get("paths") or {}).get("screenshot"),
    }
