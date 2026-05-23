"""Per-device options-flow cards and the new player-driven snapshot.

Pins the 0.3.6 contract:
- Options flow exposes a card per device.
- A card's submit only touches that device's CONF_* keys; everything
  else (other cards, tuning, legacy data values) stays put.
- An empty card submit (the "Skip" semantic) does not wipe existing
  values.
- The coordinator reads player attributes (`source`, `media_title`,
  `volume_level`, …) instead of separate `*_source_entity` entities.
- Legacy CONF keys still work — old entries don't need migration.
- Switch handheld candidate is derived diagnostically and never
  promoted to a dominant context.
"""
from __future__ import annotations

import asyncio
import types
from functools import wraps

import pytest

import tests.benni_media_context.test_module_smoke as smoke  # noqa: E402
import tests.benni_media_context.test_options_sources_menu as menu_test  # noqa: E402

flow_module = smoke.flow_module


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


_FakeOptionsFlow = menu_test._FakeOptionsFlow
_entry = menu_test._entry


def _schema_keys(schema) -> set[str]:
    return {str(getattr(m, "schema", m)) for m in schema.schema}


# ---------------------------------------------------------------------------
# 1) Menu surfaces each device + cards render only that device's keys.
# ---------------------------------------------------------------------------


_DEVICE_KEYS = {
    "tv": {"tv_player_entity", "tv_active_entity", "tv_power_entity"},
    "appletv": {"appletv_player_entity"},
    "ps5": {
        "ps5_player_entity", "ps5_active_entity", "ps5_power_entity",
        "ps5_title_entity", "ps5_network_entity",
    },
    "switch": {"switch_active_entity", "switch_power_entity", "switch_ping_entity"},
    "pc": {"pc_active_entity", "pc_power_entity"},
    "denon": {"denon_player_entity", "denon_active_entity", "denon_power_entity"},
    "homepods": {"homepods_player_entity"},
}


@pytest.mark.parametrize("card,expected_keys", list(_DEVICE_KEYS.items()))
@_run
async def test_device_card_schema_only_contains_that_device_keys(card, expected_keys):
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    step = getattr(helper, f"async_step_{card}")
    await step()
    assert helper.flow.last_form["step_id"] == card
    assert _schema_keys(helper.flow.last_form["data_schema"]) == expected_keys


# ---------------------------------------------------------------------------
# 2) Card submit only writes its own keys; other options stay intact.
# ---------------------------------------------------------------------------


@_run
async def test_card_submit_does_not_touch_other_devices_or_tuning():
    """User edits the TV card. PS5 entity assigned earlier and the
    `debounce_seconds` tuning value must survive untouched."""
    entry = _entry(options={
        "ps5_player_entity": "media_player.living_ps5",
        "debounce_seconds": 5,
    })
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_tv({
        "tv_player_entity": "media_player.living_lgtv",
        "tv_active_entity": "binary_sensor.living_tv_plug_power_active_atomic",
        "tv_power_entity": "sensor.living_tv_plug_power_atomic",
    })
    saved = helper.flow.created_entry["data"]
    assert saved["tv_player_entity"] == "media_player.living_lgtv"
    assert saved["ps5_player_entity"] == "media_player.living_ps5"
    assert saved["debounce_seconds"] == 5


@_run
async def test_empty_card_submit_does_not_clear_existing_options_for_other_devices():
    """Submitting an empty TV card (the "Skip" semantic for edit) must
    NOT delete a previously saved PS5 slot."""
    entry = _entry(options={
        "ps5_player_entity": "media_player.living_ps5",
    })
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_tv({})  # empty submit ≈ skip
    saved = helper.flow.created_entry["data"]
    assert saved["ps5_player_entity"] == "media_player.living_ps5"
    # TV keys not present because nothing was set in this card.
    assert "tv_player_entity" not in saved


@_run
async def test_clearing_a_card_slot_drops_it_so_legacy_data_falls_through():
    """If the user clears the TV player slot in the card, the resulting
    options dict should NOT carry a None/"" value — that would mask
    any legacy entry.data fallback the coordinator uses."""
    entry = _entry(
        data={"tv_active": "binary_sensor.legacy_tv_active"},
        options={"tv_player_entity": "media_player.was_set_earlier"},
    )
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_tv({"tv_player_entity": None})
    saved = helper.flow.created_entry["data"]
    assert "tv_player_entity" not in saved
    # Other device's keys untouched.
    assert "ps5_player_entity" not in saved
