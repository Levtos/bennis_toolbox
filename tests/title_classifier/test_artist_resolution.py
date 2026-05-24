"""Title Classifier: artist resolution from media_player attributes.

Pins the v0.3.6.6 behaviour:
- The configured ``CONF_ARTIST_ATTRIBUTE`` wins when set and present.
- ``ARTIST_ATTRIBUTE_CANDIDATES`` covers the common cases:
  Music Assistant exposes ``artist`` (not ``media_artist``); classic
  media_player integrations expose ``media_artist``.
- For ``media`` watchers only, when no track-level artist is reported,
  fall back to the radio-station name so panel grouping still works
  ("WDR 2 POP. Die Abendshow…" → grouped under "WDR 2 Bergisches Land",
  not under "— Kein Künstler —").
- ``game`` / ``activity`` watchers do NOT use the radio fallback —
  the synthetic key is media-specific.
"""
from __future__ import annotations

import tc_runtime as R


class _State:
    """Minimal stand-in for `homeassistant.core.State`."""

    def __init__(self, state: str, attributes: dict | None = None) -> None:
        self.state = state
        self.attributes = dict(attributes or {})


class _Entry:
    def __init__(self, watcher_type: str = "media",
                 source: str = "media_player.homepods",
                 name: str = "homepods",
                 artist_attribute: str | None = None,
                 auto_hide_hours: int | None = None) -> None:
        self.entry_id = "wid"
        self.data = {
            "name": name,
            "source_entity": source,
            "watcher_type": watcher_type,
        }
        if artist_attribute is not None:
            self.data["artist_attribute"] = artist_attribute
        self.options = {}
        if auto_hide_hours is not None:
            self.options["auto_hide_hours"] = auto_hide_hours


def _make_runtime(entry: _Entry) -> R.WatcherRuntime:
    """Bypass ``__init__`` so we don't drag the storage stub into
    this test — we only exercise the pure ``key_from_state`` path."""
    rt = R.WatcherRuntime.__new__(R.WatcherRuntime)
    rt.hass = None
    rt.entry = entry
    rt.current_key = None
    rt.current_enum = None
    rt._remove_listener = None
    rt._listeners = []
    return rt


# ---------------------------------------------------------------------------
# 1) Music Assistant uses `artist`, classic players use `media_artist`.
# ---------------------------------------------------------------------------


def test_music_assistant_artist_attribute_is_picked_up():
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "We Are The People",
        "artist": "Empire Of The Sun",  # MA exposes this name, not media_artist
        "radio_station_name": "GAYFM",
    })
    assert rt.key_from_state(state) == "Empire Of The Sun - We Are The People"


def test_classic_media_artist_still_works():
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "Time after time",
        "media_artist": "Cyndi Lauper",
    })
    assert rt.key_from_state(state) == "Cyndi Lauper - Time after time"


def test_configured_artist_attribute_takes_precedence():
    rt = _make_runtime(_Entry(artist_attribute="custom_artist_attr"))
    state = _State("playing", {
        "media_title": "Save My Love",
        "custom_artist_attr": "Kygo feat. Khalid & Gryffin",
        "artist": "should be ignored",
        "media_artist": "also ignored",
    })
    assert rt.key_from_state(state) == "Kygo feat. Khalid & Gryffin - Save My Love"


def test_album_artist_used_when_only_album_artist_present():
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "Untitled Demo",
        "album_artist": "Various Artists",
    })
    assert rt.key_from_state(state) == "Various Artists - Untitled Demo"


# ---------------------------------------------------------------------------
# 2) Radio fallback: use station name as synthetic artist for media watchers.
# ---------------------------------------------------------------------------


def test_radio_without_artist_falls_back_to_station_name():
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "1LIVE Fiehe",
        "artist": None,
        "radio_station_name": "1LIVE",
    })
    assert rt.key_from_state(state) == "1LIVE - 1LIVE Fiehe"


def test_wdr_radio_show_groups_under_station():
    """The Einhornzentrale ask: 'WDR 2 POP. Die Abendshow…' should
    end up grouped under WDR 2 Bergisches Land, not lost."""
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "WDR 2 POP. Die Abendshow mit Marcus Barsch",
        "radio_station_name": "WDR 2 Bergisches Land",
    })
    assert rt.key_from_state(state) == (
        "WDR 2 Bergisches Land - WDR 2 POP. Die Abendshow mit Marcus Barsch"
    )


def test_classical_recording_with_long_artist_chain_uses_real_artist():
    """When BOTH artist and radio station are present, the real
    track-level artist still wins."""
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "Rondeau. Tempo di minuetto, aus: Konzert F-dur",
        "artist": "Hiroaki Mizuma/ Kölner Rundfunkorchester",
        "radio_station_name": "WDR 4",
    })
    assert rt.key_from_state(state) == (
        "Hiroaki Mizuma/ Kölner Rundfunkorchester - Rondeau. Tempo di minuetto, "
        "aus: Konzert F-dur"
    )


def test_radio_station_alias_attributes_are_also_tried():
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "Some Show",
        "media_station": "BBC Radio 4",
    })
    assert rt.key_from_state(state) == "BBC Radio 4 - Some Show"


def test_no_artist_and_no_station_yields_bare_title():
    """Last resort: nothing to group by → bare title key, same as
    pre-0.3.6.6 behaviour."""
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "Mystery Track",
    })
    assert rt.key_from_state(state) == "Mystery Track"


# ---------------------------------------------------------------------------
# 3) Radio fallback is media-specific, not for game/activity.
# ---------------------------------------------------------------------------


def test_game_watcher_does_not_use_radio_station_fallback():
    """Game watchers shouldn't try to use radio station names as a
    "game artist" — they return the bare title (game_name)."""
    rt = _make_runtime(_Entry(watcher_type="game"))
    state = _State("playing", {
        "media_title": "Some Game Title",
        "radio_station_name": "WDR 2",
    })
    assert rt.key_from_state(state) == "Some Game Title"


def test_activity_watcher_does_not_use_radio_station_fallback():
    rt = _make_runtime(_Entry(watcher_type="activity"))
    state = _State("running", {
        "activity": "Walking",
        "radio_station_name": "WDR 2",
    })
    assert rt.key_from_state(state) == "Walking"


# ---------------------------------------------------------------------------
# 4) Cleaning still applies (empty / unknown values are ignored).
# ---------------------------------------------------------------------------


def test_empty_string_artist_is_ignored_and_station_takes_over():
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "Save My Love",
        "artist": "",                   # empty → skip
        "media_artist": "unknown",      # cleaned away
        "radio_station_name": "Jack FM - Berlin",
    })
    assert rt.key_from_state(state) == "Jack FM - Berlin - Save My Love"


def test_unknown_station_name_does_not_pollute_key():
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "Mystery Track",
        "radio_station_name": "unavailable",
    })
    # Cleaned away → no artist → bare title.
    assert rt.key_from_state(state) == "Mystery Track"


# ---------------------------------------------------------------------------
# 5) Internal-ID heuristic — protect against a mis-configured
#    `artist_attribute` (the Einhornzentrale case where the user picked
#    `active_queue` and every panel entry got prefixed with
#    `syncgroup_edfgeqne - …`).
# ---------------------------------------------------------------------------


def test_looks_like_internal_id_recognises_mass_syncgroup():
    f = R._looks_like_internal_id
    assert f("syncgroup_edfgeqne") is True
    assert f("syncgroup-edfgeqne") is True
    assert f("mass_player_abc") is True
    assert f("ma_queue_42") is True
    assert f("queue_xyz") is True


def test_looks_like_internal_id_recognises_uuids():
    f = R._looks_like_internal_id
    assert f("960eb9c7-0601-11e8-ae97-52543be04c81") is True
    assert f("960eb9c7060111e8ae9752543be04c81") is True


def test_looks_like_internal_id_recognises_opaque_tokens():
    f = R._looks_like_internal_id
    assert f("edfgeqne") is True               # all lowercase, no spaces
    assert f("abc_def_ghi") is True
    assert f("hash_abcd1234ef") is True


def test_looks_like_internal_id_lets_real_artists_through():
    f = R._looks_like_internal_id
    # Spaces → human name
    assert f("Becky Hill feat. Shift K3Y") is False
    assert f("Daft Punk") is False
    assert f("Hiroaki Mizuma/ Kölner Rundfunkorchester") is False
    assert f("WDR 4") is False
    assert f("1LIVE") is False                  # mixed case + digit
    assert f("Jack FM - Berlin") is False       # spaces
    assert f("Pro7") is False                   # mixed case
    assert f("ARD") is False                    # all caps (short)


def test_mis_configured_active_queue_falls_through_to_media_artist():
    """The exact Einhornzentrale failure mode: the user picked
    `active_queue` as artist_attribute at setup time, so for every
    song the runtime produced `syncgroup_edfgeqne - <title>`. With
    the heuristic, the opaque internal ID is rejected and the
    runtime falls back to the real `media_artist` value."""
    rt = _make_runtime(_Entry(artist_attribute="active_queue"))
    state = _State("playing", {
        "media_title": "Better Off Without You",
        "media_artist": "Becky Hill feat. Shift K3Y",
        "active_queue": "syncgroup_edfgeqne",
    })
    assert rt.key_from_state(state) == (
        "Becky Hill feat. Shift K3Y - Better Off Without You"
    )


def test_mis_configured_attribute_with_no_fallback_returns_bare_title():
    """If the bad attribute is the ONLY signal, we drop to bare title
    instead of poisoning the panel with the opaque ID."""
    rt = _make_runtime(_Entry(artist_attribute="active_queue"))
    state = _State("playing", {
        "media_title": "Some Track",
        "active_queue": "syncgroup_edfgeqne",
    })
    assert rt.key_from_state(state) == "Some Track"


def test_internal_id_in_radio_station_name_is_also_rejected():
    """Defensive: even the radio-station fallback shouldn't accept an
    opaque ID. Better a bare title than a confusing grouping key."""
    rt = _make_runtime(_Entry())
    state = _State("playing", {
        "media_title": "Some Track",
        "radio_station_name": "syncgroup_edfgeqne",
    })
    assert rt.key_from_state(state) == "Some Track"
