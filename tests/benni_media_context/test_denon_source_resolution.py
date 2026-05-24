"""v0.3.6.3 hotfix: Denon source comes from the media_player, never
from a legacy active-binary that happens to wrap a power sensor.

Pin the resolution rules:
- If `denon_player_entity` is configured → source = its `source` attr.
- Otherwise → fall back to the `source` attr of the legacy
  `denon_active` slot (some users wire a media_player into it).
- Power-sensor entity IDs (and binary-sensor states) never surface
  as `denon_source` — only `source` *attributes* are read, and a
  power sensor has none.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest


MODULE_DIR = Path(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
) / "custom_components" / "bennis_toolbox" / "modules" / "benni_media_context"


# Reuse the heavy HA + toolbox stubs from the smoke test (it already
# installs config_entries / sensor / binary_sensor / helpers.selector
# / data_entry_flow stubs), plus the flattening test which installs
# the missing helpers.event + helpers.update_coordinator stubs.
import tests.benni_media_context.test_module_smoke as _smoke  # noqa: F401, E402
import tests.benni_media_context.test_entity_flattening as _flatten  # noqa: F401, E402

# After those imports, `bmc_coord_for_flatten` is loaded which is
# already the real coordinator module under another alias — reuse it
# directly so we don't double-load.
coord_module = sys.modules["bmc_coord_for_flatten"]


# ---------------------------------------------------------------------------
# Minimal fakes for hass.states + a coordinator-shaped object so we can
# call `_build_snapshot` directly without spinning up HA.
# ---------------------------------------------------------------------------


class _State:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class _States:
    def __init__(self, mapping):
        self._m = dict(mapping)

    def get(self, entity_id):
        return self._m.get(entity_id)


class _Entry:
    def __init__(self, data=None, options=None):
        self.data = dict(data or {})
        self.options = dict(options or {})
        self.entry_id = "test"


def _make_coordinator(*, hass_states, entry_data=None, entry_options=None):
    """Build a coordinator instance just well enough to call
    `_build_snapshot` without going through `__init__` (which wants
    a real DataUpdateCoordinator wiring)."""
    Coord = coord_module.BenniMediaCoordinator
    coord = Coord.__new__(Coord)  # bypass __init__
    coord.hass = types.SimpleNamespace(states=_States(hass_states))
    coord.entry = _Entry(entry_data, entry_options)
    coord._manual_nudge = None
    coord._pre_atv_scenario = None
    coord._last_snapshot = None
    return coord


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_denon_source_comes_from_player_attribute_when_player_configured():
    """The Einhornzentrale case: denon_player_entity points to
    media_player.living_denon whose `source` attribute is "TV Audio".
    A legacy `denon_active` slot also exists, wired to a power binary
    — that one must NOT shadow the player's source."""
    coord = _make_coordinator(
        hass_states={
            "media_player.living_denon": _State("on", {"source": "TV Audio"}),
            "binary_sensor.living_denon_plug_power_active_atomic": _State(
                "on", {}  # plug binary has no `source` attr
            ),
        },
        entry_data={
            # Legacy slot still set from the old config.
            "denon_active": "binary_sensor.living_denon_plug_power_active_atomic",
        },
        entry_options={
            # New per-device card values.
            "denon_player_entity": "media_player.living_denon",
        },
    )
    snap = coord._build_snapshot()
    assert snap.denon_source == "TV Audio"
    assert snap.denon_active is True


def test_denon_source_falls_back_to_legacy_when_no_player_configured():
    """No `denon_player_entity` configured at all. Some legacy setups
    wired a media_player into the `denon_active` slot — keep reading
    its `source` attr in that case so existing setups stay working."""
    coord = _make_coordinator(
        hass_states={
            "media_player.living_denon": _State("on", {"source": "PC"}),
        },
        entry_data={
            "denon_active": "media_player.living_denon",
        },
    )
    snap = coord._build_snapshot()
    assert snap.denon_source == "PC"


def test_denon_source_is_none_when_legacy_active_is_a_binary_sensor():
    """No new player configured; legacy slot is a binary_sensor on a
    power-meter. Binary sensors have no `source` attr → denon_source
    stays None (it's NEVER the entity ID of the power sensor)."""
    coord = _make_coordinator(
        hass_states={
            "binary_sensor.living_denon_plug_power_active_atomic": _State(
                "on", {}
            ),
            "sensor.living_denon_plug_power_atomic": _State("44.0", {}),
        },
        entry_data={
            "denon_active": "binary_sensor.living_denon_plug_power_active_atomic",
        },
    )
    snap = coord._build_snapshot()
    assert snap.denon_source is None
    # But denon_active still gets set from the binary plug signal.
    assert snap.denon_active is True


def test_denon_player_source_wins_even_when_legacy_active_present():
    """User has both wired up: new player AND legacy active slot.
    The player must win — that's the whole point of the migration."""
    coord = _make_coordinator(
        hass_states={
            "media_player.living_denon": _State("on", {"source": "Spotify"}),
            "binary_sensor.living_denon_plug_power_active_atomic": _State("on", {}),
        },
        entry_data={
            # Legacy slot is set on entry.data
            "denon_active": "binary_sensor.living_denon_plug_power_active_atomic",
        },
        entry_options={
            "denon_player_entity": "media_player.living_denon",
        },
    )
    snap = coord._build_snapshot()
    assert snap.denon_source == "Spotify"
