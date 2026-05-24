"""v0.3.6.5 regression: device_diagnostics propagates from snapshot
into the Decision (and thus through `async_set_updated_data` to the
entity attributes).

Until 0.3.6.4 the Decision dataclass did not carry a
`device_diagnostics` field at all, so the coordinator's per-device
diagnostic dict was built but never published to consumers. The
entity attribute view showed `{}` permanently.

This file pins:
- Decision now carries `device_diagnostics`.
- `decide()` copies the snapshot's diag into the returned Decision
  in BOTH the quiet early-return and the main branch.
- Diagnostics are filled for every configured device card, even
  when the device is off.
- The `resolution_source` flag correctly distinguishes new keys
  from legacy fallbacks.
- The two diagnostic entities (`media_context`, `media_device`)
  expose identical diag dicts.
"""
from __future__ import annotations

import sys

import pytest

# Load logic via the existing conftest aliases.
import bmc_logic as L
import bmc_const as C

# And the real coordinator via the flatten-test aliases.
import tests.benni_media_context.test_entity_flattening as _flatten  # noqa: F401
import tests.benni_media_context.test_denon_source_resolution as denon_test  # noqa: F401

coord_module = sys.modules["bmc_coord_for_flatten"]


DEFAULT_OPTS = dict(
    app_map=C.DEFAULT_APPLETV_APP_MAP,
    base_homepods=0.35,
    base_denon=0.40,
    boost_offset=0.10,
    window_offset=-0.05,
    quiet_duck=0.15,
)


# ---------------------------------------------------------------------------
# 1) Decision carries device_diagnostics, populated from the Snapshot.
# ---------------------------------------------------------------------------


def test_decision_dataclass_declares_device_diagnostics_field():
    """Static contract: the Decision dataclass must own the field so
    `coordinator.data.device_diagnostics` doesn't fall back to {}."""
    d = L.Decision()
    assert hasattr(d, "device_diagnostics")
    assert d.device_diagnostics == {}


def test_decide_copies_snapshot_diagnostics_into_decision():
    snap = L.Snapshot()
    snap.device_diagnostics = {
        "pc": {"configured_active_entity": "binary_sensor.pc_active",
               "resolution_source": "new_key"},
    }
    d = L.decide(snap, **DEFAULT_OPTS)
    assert d.device_diagnostics == {
        "pc": {"configured_active_entity": "binary_sensor.pc_active",
               "resolution_source": "new_key"},
    }


def test_decide_copies_snapshot_diagnostics_even_in_quiet_path():
    """The quiet-mode early-return must also carry diag forward —
    otherwise a call/door event would erase the panel."""
    snap = L.Snapshot()
    snap.call_active = True
    snap.device_diagnostics = {
        "tv": {"configured_player_entity": "media_player.living_lgtv",
               "resolution_source": "new_key"},
    }
    d = L.decide(snap, **DEFAULT_OPTS)
    assert d.quiet_mode_active is True
    assert d.device_diagnostics == {
        "tv": {"configured_player_entity": "media_player.living_lgtv",
               "resolution_source": "new_key"},
    }


# ---------------------------------------------------------------------------
# 2) Coordinator-side: configured device cards fill diagnostics even
#    when the device is OFF.
# ---------------------------------------------------------------------------


def _make_coord(states, *, data=None, options=None):
    Coord = coord_module.BenniMediaCoordinator
    coord = Coord.__new__(Coord)
    import types as _types
    coord.hass = _types.SimpleNamespace(
        states=denon_test._States(states),
    )
    coord.entry = denon_test._Entry(data, options)
    coord._manual_nudge = None
    coord._pre_atv_scenario = None
    coord._last_snapshot = None
    return coord


def test_pc_diagnostics_present_when_pc_active_binary_on():
    """The Einhornzentrale repro: PC active binary is on; the runtime
    correctly resolves the device as `pc` AND the diag dict carries
    a populated `pc` bucket."""
    coord = _make_coord(
        states={
            "binary_sensor.living_pc_plug_power_active_atomic": denon_test._State("on", {}),
            "sensor.living_pc_plug_power_atomic": denon_test._State("65.0", {}),
        },
        options={
            "pc_active_entity": "binary_sensor.living_pc_plug_power_active_atomic",
            "pc_power_entity": "sensor.living_pc_plug_power_atomic",
        },
    )
    snap = coord._build_snapshot()
    decision = L.decide(snap, **DEFAULT_OPTS)
    assert decision.device == C.DEV_PC
    assert decision.context == C.CTX_GAMING
    # device_diagnostics must be on the published decision now.
    diag = decision.device_diagnostics
    assert "pc" in diag
    pc = diag["pc"]
    assert pc["configured_active_entity"] == "binary_sensor.living_pc_plug_power_active_atomic"
    assert pc["configured_power_entity"] == "sensor.living_pc_plug_power_atomic"
    assert pc["active_state"] is True
    assert pc["power_w"] == 65.0
    assert pc["resolution_source"] == "new_key"


def test_denon_diagnostics_filled_even_when_player_off():
    """A configured Denon card whose player is currently `off` must
    still show up in diag with player_state == "off"."""
    coord = _make_coord(
        states={
            "media_player.living_denon": denon_test._State("off", {}),
        },
        options={"denon_player_entity": "media_player.living_denon"},
    )
    snap = coord._build_snapshot()
    decision = L.decide(snap, **DEFAULT_OPTS)
    diag = decision.device_diagnostics["denon"]
    assert diag["configured_player_entity"] == "media_player.living_denon"
    # `_record` populates player_state via _state_of, which strips
    # "unavailable"/"unknown" only — "off" passes through.
    assert diag["player_state"] == "off"
    assert diag["resolution_source"] == "new_key"


def test_tv_and_homepods_diag_present_even_with_no_states_in_hass():
    """Card configured but the entity hasn't reported any state yet
    (entity in hass.states absent → all reads return None). The diag
    must still mark the configured entity and `resolution_source =
    new_key` so the panel reflects what the user typed."""
    coord = _make_coord(
        states={},
        options={
            "tv_player_entity": "media_player.living_lgtv",
            "homepods_player_entity": "media_player.homepod_group",
        },
    )
    snap = coord._build_snapshot()
    decision = L.decide(snap, **DEFAULT_OPTS)
    tv = decision.device_diagnostics["tv"]
    hp = decision.device_diagnostics["homepods"]
    assert tv["configured_player_entity"] == "media_player.living_lgtv"
    assert tv["resolution_source"] == "new_key"
    assert hp["configured_player_entity"] == "media_player.homepod_group"
    assert hp["resolution_source"] == "new_key"


def test_legacy_only_config_marks_legacy_fallback():
    """Pure legacy entry: only `pc_active` set on entry.data, no new
    `pc_active_entity`. diag should record `legacy_fallback`."""
    coord = _make_coord(
        states={
            "binary_sensor.legacy_pc_active": denon_test._State("on", {}),
        },
        data={"pc_active": "binary_sensor.legacy_pc_active"},
    )
    snap = coord._build_snapshot()
    decision = L.decide(snap, **DEFAULT_OPTS)
    pc = decision.device_diagnostics["pc"]
    assert pc["configured_active_entity"] == "binary_sensor.legacy_pc_active"
    assert pc["resolution_source"] == "legacy_fallback"


def test_new_plus_legacy_picks_new_and_diag_reports_new_key():
    coord = _make_coord(
        states={
            "binary_sensor.new_pc_active": denon_test._State("on", {}),
            "binary_sensor.legacy_pc_active": denon_test._State("off", {}),
        },
        data={"pc_active": "binary_sensor.legacy_pc_active"},
        options={"pc_active_entity": "binary_sensor.new_pc_active"},
    )
    snap = coord._build_snapshot()
    decision = L.decide(snap, **DEFAULT_OPTS)
    pc = decision.device_diagnostics["pc"]
    assert pc["configured_active_entity"] == "binary_sensor.new_pc_active"
    assert pc["resolution_source"] == "new_key"
    # And the runtime actually used the new one — pc_active reflects "on".
    assert snap.pc_active is True
    assert decision.device == C.DEV_PC


# ---------------------------------------------------------------------------
# 3) media_context and media_device sensors expose identical diag dicts.
# ---------------------------------------------------------------------------


def test_context_and_device_sensors_share_device_diagnostics():
    """Read the entity source to confirm both sensors' extra_state_
    attributes pull from the same field on `coordinator.data`."""
    import os
    from pathlib import Path
    repo = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    src = (repo / "custom_components/bennis_toolbox/modules/benni_media_context/entities.py").read_text(encoding="utf-8")
    # Both sensors must include the diag-attribute exposure block.
    ctx_block = src.split("class _ContextSensor")[1].split("class _SubcontextSensor")[0]
    dev_block = src.split("class _DeviceSensor")[1].split("class _GamingSourceSensor")[0]
    for label, block in (("media_context", ctx_block), ("media_device", dev_block)):
        assert "device_diagnostics" in block, label
        assert "self.coordinator.data" in block, label
