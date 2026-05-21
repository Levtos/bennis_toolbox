"""Tests for the pure playback-detection helpers in playback_logic.py."""

from __future__ import annotations

import pytest

import sh_const as C
import sh_playback as P


# --------------------------------------------------------- rewrite_url


def test_rewrite_url_swaps_authority_keeps_path():
    base = "https://stash.example.com:8443"
    url = "http://internal-stash:9999/scene/123/screenshot?token=abc"
    rewritten = P.rewrite_url(base, url)
    assert rewritten == "https://stash.example.com:8443/scene/123/screenshot?token=abc"


def test_rewrite_url_handles_relative_path():
    base = "https://stash.example.com:8443"
    assert P.rewrite_url(base, "/scene/1") == "https://stash.example.com:8443/scene/1"
    assert P.rewrite_url(base, "scene/1") == "https://stash.example.com:8443/scene/1"


# --------------------------------------------------------- parse_play_duration


@pytest.mark.parametrize("raw,expected", [
    (12.5, 12.5),
    ("8.3", 8.3),
    (None, 0.0),
    ("garbage", 0.0),
    (0, 0.0),
])
def test_parse_play_duration_normalises(raw, expected):
    assert P.parse_play_duration(raw) == expected


# --------------------------------------------------------- is_streaming


def test_is_streaming_within_grace_window():
    now = 1000.0
    assert P.is_streaming(now - 10.0, now) is True
    # Grace window is STREAM_ACTIVITY_GRACE_SECONDS = 60.
    assert P.is_streaming(now - 59.9, now) is True
    assert P.is_streaming(now - 60.1, now) is False
    assert P.is_streaming(None, now) is False


# --------------------------------------------------------- evaluate_scene_signal


def test_first_observation_fresh_play_is_streaming():
    now = 1000.0
    result = P.evaluate_scene_signal(
        play_duration=42.0,
        prev_signal=None,
        last_played_age_s=5.0,
        now_ts=now,
    )
    assert result["fresh_first_seen"] is True
    assert result["last_activity_ts"] == now
    assert result["streaming"] is True


def test_first_observation_stale_play_is_idle():
    now = 1000.0
    result = P.evaluate_scene_signal(
        play_duration=42.0,
        prev_signal=None,
        last_played_age_s=300.0,  # well past FRESH threshold
        now_ts=now,
    )
    assert result["fresh_first_seen"] is False
    assert result["last_activity_ts"] is None
    assert result["streaming"] is False


def test_play_duration_advance_marks_streaming():
    now = 1000.0
    result = P.evaluate_scene_signal(
        play_duration=50.0,
        prev_signal={"play_duration": 40.0, "last_activity_ts": now - 30},
        last_played_age_s=120.0,
        now_ts=now,
    )
    assert result["delta_advanced"] is True
    assert result["last_activity_ts"] == now
    assert result["streaming"] is True


def test_play_duration_stagnates_keeps_prev_activity_ts():
    now = 1000.0
    result = P.evaluate_scene_signal(
        play_duration=40.0,
        prev_signal={"play_duration": 40.0, "last_activity_ts": now - 30},
        last_played_age_s=120.0,
        now_ts=now,
    )
    assert result["delta_advanced"] is False
    # last_activity_ts is preserved → still streaming within the grace window.
    assert result["last_activity_ts"] == now - 30
    assert result["streaming"] is True


def test_play_duration_stagnates_past_grace_drops_to_idle():
    now = 1000.0
    result = P.evaluate_scene_signal(
        play_duration=40.0,
        prev_signal={"play_duration": 40.0, "last_activity_ts": now - 200},
        last_played_age_s=600.0,
        now_ts=now,
    )
    assert result["streaming"] is False


# --------------------------------------------------------- prune_stale_signals


def test_prune_stale_signals_keeps_seen_and_drops_old():
    now = 1000.0
    signals = {
        "a": {"play_duration": 1.0, "last_activity_ts": now - 30},
        "b": {"play_duration": 2.0, "last_activity_ts": now - 500},  # very stale
        "c": {"play_duration": 3.0, "last_activity_ts": now - 30},
    }
    P.prune_stale_signals(signals, seen_ids={"a"}, now_ts=now)
    # `a` was just seen, keeps state. `b` was not seen and is past 2*grace → drop.
    # `c` was not seen but is still inside 2*grace → keep.
    assert set(signals) == {"a", "c"}


# --------------------------------------------------------- summarise_last_played


def test_summarise_last_played_picks_useful_fields():
    scene = {
        "id": "42",
        "title": "Test",
        "last_played_at": "2026-01-12T09:00:00+00:00",
        "studio": {"name": "Studio A"},
        "performers": [{"name": "X"}, {"name": "Y"}, {"name": ""}],
        "paths": {"screenshot": "https://stash.example.com/screens/42.jpg"},
    }
    out = P.summarise_last_played(scene)
    assert out == {
        "id": "42",
        "title": "Test",
        "last_played_at": "2026-01-12T09:00:00+00:00",
        "studio": "Studio A",
        "performers": ["X", "Y"],
        "screenshot": "https://stash.example.com/screens/42.jpg",
    }


def test_summarise_handles_missing_pieces_gracefully():
    out = P.summarise_last_played({"id": "1", "title": None})
    assert out["studio"] is None
    assert out["performers"] == []
    assert out["screenshot"] is None
