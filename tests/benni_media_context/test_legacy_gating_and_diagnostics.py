"""v0.3.6.4 hotfix tests.

1. The legacy "sources" / "Auslöser & Quellen" step is gated:
   - fresh entries never see it in the menu,
   - entries with any legacy CONF value still surface it so users can
     migrate.
2. device_diagnostics exposes `configured_*_entity` and
   `resolution_source` per device, distinguishing new keys from legacy
   fallbacks.
3. Denon source still comes from the media_player attribute, never the
   power-sensor entity ID (regression for 0.3.6.3 carried forward).
"""
from __future__ import annotations

import asyncio
import sys
import types
from functools import wraps

import pytest

import tests.benni_media_context.test_module_smoke as smoke  # noqa: E402
import tests.benni_media_context.test_options_sources_menu as menu_test  # noqa: E402
import tests.benni_media_context.test_entity_flattening as _flatten  # noqa: F401, E402
import tests.benni_media_context.test_denon_source_resolution as denon_test  # noqa: E402

flow_module = smoke.flow_module
_FakeOptionsFlow = menu_test._FakeOptionsFlow
_entry = menu_test._entry

# The real coordinator module is loaded by test_entity_flattening
# under "bmc_coord_for_flatten" — reuse it here too.
coord_module = sys.modules["bmc_coord_for_flatten"]


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# ---------------------------------------------------------------------------
# 1) Legacy `sources` menu gating.
# ---------------------------------------------------------------------------


@_run
async def test_fresh_entry_does_not_offer_legacy_sources_step():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_init()
    opts = helper.flow.last_menu["menu_options"]
    assert "sources" not in opts


@_run
async def test_entry_with_legacy_values_in_data_offers_sources_step():
    """Migration scenario: user has the historic `tv_active` slot set
    in entry.data → the legacy aggregate step is offered so they can
    review and clean it up."""
    entry = _entry(data={"tv_active": "binary_sensor.legacy_tv_active"})
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_init()
    opts = helper.flow.last_menu["menu_options"]
    assert "sources" in opts


@_run
async def test_entry_with_legacy_values_in_options_offers_sources_step():
    entry = _entry(options={"homepods": ["media_player.x"]})
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_init()
    opts = helper.flow.last_menu["menu_options"]
    assert "sources" in opts


@_run
async def test_only_new_keys_does_not_offer_sources_step():
    """User configured the new per-device cards exclusively. The legacy
    aggregate stays hidden — it would only confuse a clean setup."""
    entry = _entry(options={
        "tv_player_entity": "media_player.living_lgtv",
        "denon_player_entity": "media_player.living_denon",
    })
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_init()
    opts = helper.flow.last_menu["menu_options"]
    assert "sources" not in opts


@_run
async def test_sources_label_is_marked_legacy_in_translations():
    """The user-visible label for the gated step must signal that it's
    a legacy/migration-only surface, not the normal way to configure
    sources."""
    import json
    from pathlib import Path
    import os
    repo = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    de = json.loads((repo / "custom_components/bennis_toolbox/translations/de.json").read_text(encoding="utf-8"))
    en = json.loads((repo / "custom_components/bennis_toolbox/translations/en.json").read_text(encoding="utf-8"))
    de_label = de["options"]["step"]["init"]["menu_options"]["sources"].lower()
    en_label = en["options"]["step"]["init"]["menu_options"]["sources"].lower()
    assert "legacy" in de_label or "altbestand" in de_label, de_label
    assert "legacy" in en_label, en_label


# ---------------------------------------------------------------------------
# 2) device_diagnostics with configured_* + resolution_source.
# ---------------------------------------------------------------------------


def _make_coord(states, *, data=None, options=None):
    Coord = coord_module.BenniMediaCoordinator
    coord = Coord.__new__(Coord)
    coord.hass = types.SimpleNamespace(
        states=denon_test._States(states),
    )
    coord.entry = denon_test._Entry(data, options)
    coord._manual_nudge = None
    coord._pre_atv_scenario = None
    coord._last_snapshot = None
    return coord


def test_device_diagnostics_records_configured_entities_for_new_keys():
    coord = _make_coord(
        states={
            "media_player.living_denon": denon_test._State("on", {"source": "TV Audio"}),
            "binary_sensor.living_denon_plug_power_active_atomic": denon_test._State("on", {}),
            "sensor.living_denon_plug_power_atomic": denon_test._State("44.0", {}),
        },
        options={
            "denon_player_entity": "media_player.living_denon",
            "denon_active_entity": "binary_sensor.living_denon_plug_power_active_atomic",
            "denon_power_entity": "sensor.living_denon_plug_power_atomic",
        },
    )
    snap = coord._build_snapshot()
    denon = snap.device_diagnostics["denon"]
    assert denon["configured_player_entity"] == "media_player.living_denon"
    assert denon["configured_active_entity"] == "binary_sensor.living_denon_plug_power_active_atomic"
    assert denon["configured_power_entity"] == "sensor.living_denon_plug_power_atomic"
    assert denon["resolution_source"] == "new_key"
    assert denon["source"] == "TV Audio"


def test_device_diagnostics_flags_legacy_fallback_when_only_legacy_set():
    coord = _make_coord(
        states={
            "binary_sensor.legacy_denon_active": denon_test._State("on", {}),
        },
        data={
            # Legacy slot only — no new key in options.
            "denon_active": "binary_sensor.legacy_denon_active",
        },
    )
    snap = coord._build_snapshot()
    denon = snap.device_diagnostics["denon"]
    assert denon["configured_active_entity"] == "binary_sensor.legacy_denon_active"
    assert denon["resolution_source"] == "legacy_fallback"
    # No player configured → source must not surface as an entity ID.
    assert denon.get("source") in (None, "")
    assert "sensor." not in (denon.get("source") or "")


def test_new_key_wins_when_both_legacy_and_new_set():
    """Both legacy `denon_active` and new `denon_active_entity` set.
    The new key must win in the resolver and the diagnostic must
    report `new_key` (not `legacy_fallback`)."""
    coord = _make_coord(
        states={
            "binary_sensor.new_denon_active": denon_test._State("on", {}),
            "binary_sensor.legacy_denon_active": denon_test._State("off", {}),
        },
        data={"denon_active": "binary_sensor.legacy_denon_active"},
        options={"denon_active_entity": "binary_sensor.new_denon_active"},
    )
    snap = coord._build_snapshot()
    denon = snap.device_diagnostics["denon"]
    assert denon["configured_active_entity"] == "binary_sensor.new_denon_active"
    assert denon["resolution_source"] == "new_key"


# ---------------------------------------------------------------------------
# 3) Denon source authority — already covered in 0.3.6.3 but pinned again
#    against the diagnostics surface to make sure no power-sensor entity
#    ID leaks through as `source`.
# ---------------------------------------------------------------------------


def test_denon_diag_source_never_carries_power_sensor_entity_id():
    coord = _make_coord(
        states={
            "media_player.living_denon": denon_test._State("on", {"source": "PC"}),
            "sensor.living_denon_plug_power_atomic": denon_test._State("44.0", {}),
        },
        options={
            "denon_player_entity": "media_player.living_denon",
            "denon_power_entity": "sensor.living_denon_plug_power_atomic",
        },
    )
    snap = coord._build_snapshot()
    denon = snap.device_diagnostics["denon"]
    # source comes from the player, never the power-sensor entity ID.
    assert denon["source"] == "PC"
    assert "sensor." not in denon["source"]
    # The power sensor IS reported as configured + carries its value.
    assert denon["configured_power_entity"] == "sensor.living_denon_plug_power_atomic"
    assert denon["power_w"] == 44.0
