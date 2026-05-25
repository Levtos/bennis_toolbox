"""Tests for the 0.3.8 options-flow cards: 'orchestrator' + 'volume'.

The 'orchestrator' card houses the entity slots that don't fit any
existing device card (bio_state, manual_playback, planned_radio,
pc_gaming_active, media_stop_latch, opening_any_open, quiet_mode).

The 'volume' card houses the 9 tunable volume parameters. Both
cards reuse the bare-TextSelector pattern from the 0.3.7 tuning fix
for the numeric fields.
"""
from __future__ import annotations

import asyncio
from functools import wraps

import pytest

import tests.benni_media_context.test_module_smoke as smoke  # noqa: E402
import tests.benni_media_context.test_options_sources_menu as menu_test  # noqa: E402

flow_module = smoke.flow_module
_FakeOptionsFlow = menu_test._FakeOptionsFlow
_entry = menu_test._entry


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


# ---------------------------------------------------------------------------
# Menu surfaces both new cards
# ---------------------------------------------------------------------------


@_run
async def test_init_menu_lists_orchestrator_and_volume():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    result = await helper.async_step_init()
    assert result["type"] == "menu"
    opts = set(helper.flow.last_menu["menu_options"])
    assert {"orchestrator", "volume"} <= opts


# ---------------------------------------------------------------------------
# Orchestrator card
# ---------------------------------------------------------------------------


_ORCHESTRATOR_KEYS = (
    "bio_state_entity",
    "manual_playback_entity",
    "planned_radio_entity",
    "pc_gaming_active_entity",
    "media_stop_latch_entity",
    "opening_any_open_entity",
    "quiet_mode_entity",
)


@_run
async def test_orchestrator_card_renders_all_seven_slots():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_orchestrator()
    schema = helper.flow.last_form["data_schema"]
    schema_keys = {str(getattr(m, "schema", m)) for m in schema.schema}
    for key in _ORCHESTRATOR_KEYS:
        assert key in schema_keys, f"missing field {key!r}"


@_run
async def test_orchestrator_card_saves_provided_entities():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    user_input = {
        "bio_state_entity": "sensor.bio_state",
        "manual_playback_entity": "binary_sensor.user_started_music",
        "planned_radio_entity": "binary_sensor.scheduled_radio",
        "pc_gaming_active_entity": "binary_sensor.pc_is_gaming",
        "media_stop_latch_entity": "binary_sensor.media_stop_latch",
        "opening_any_open_entity": "binary_sensor.any_opening_open",
        "quiet_mode_entity": "binary_sensor.quiet_mode",
    }
    result = await helper.async_step_orchestrator(user_input)
    assert result["type"] == "create_entry"
    for key, value in user_input.items():
        assert result["data"][key] == value


@_run
async def test_orchestrator_card_drops_empty_entities():
    """Empty submissions must drop options so legacy data-side values
    can resurface — same semantics as the device cards."""
    entry = _entry(options={
        "bio_state_entity": "sensor.old_bio",
        "pc_gaming_active_entity": "binary_sensor.pc_old",
    })
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    user_input = {
        "bio_state_entity": "sensor.new_bio",
        "pc_gaming_active_entity": "",  # explicit clear
    }
    result = await helper.async_step_orchestrator(user_input)
    assert result["type"] == "create_entry"
    assert result["data"]["bio_state_entity"] == "sensor.new_bio"
    assert "pc_gaming_active_entity" not in result["data"]


# ---------------------------------------------------------------------------
# Volume card
# ---------------------------------------------------------------------------


_VOLUME_KEYS = (
    "volume_homepods_media_base",
    "volume_denon_media_base",
    "volume_ducked_target",
    "volume_homepods_max",
    "volume_denon_max",
    "volume_active_min",
    "volume_night_offset",
    "volume_edge_day_offset",
    "volume_opening_offset",
)


@_run
async def test_volume_card_renders_all_nine_fields():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_volume()
    schema = helper.flow.last_form["data_schema"]
    schema_keys = {str(getattr(m, "schema", m)) for m in schema.schema}
    for key in _VOLUME_KEYS:
        assert key in schema_keys, f"missing field {key!r}"


@_run
async def test_volume_card_defaults_render_with_dot_separator():
    """Same locale-bypass as the tuning fix — defaults must surface
    as dot-separated strings."""
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_volume()
    schema = helper.flow.last_form["data_schema"]
    defaults = {}
    for marker in schema.schema:
        name = str(getattr(marker, "schema", marker))
        if name in _VOLUME_KEYS:
            try:
                defaults[name] = marker.default()
            except Exception:
                defaults[name] = None
    assert defaults["volume_homepods_media_base"] == "0.35"
    assert defaults["volume_denon_media_base"] == "0.4"
    assert defaults["volume_night_offset"] == "-0.1"


@_run
async def test_volume_card_accepts_comma_decimal_input():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    result = await helper.async_step_volume({
        "volume_homepods_media_base": "0,40",
        "volume_night_offset": "-0,15",
    })
    assert result["type"] == "create_entry"
    assert result["data"]["volume_homepods_media_base"] == pytest.approx(0.40)
    assert result["data"]["volume_night_offset"] == pytest.approx(-0.15)


@_run
async def test_volume_card_rejects_out_of_range_with_form_errors():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    result = await helper.async_step_volume({
        "volume_homepods_max": "1.5",  # out of [0, 1]
        "volume_night_offset": "-2.0",  # out of [-0.5, 0.5]
    })
    assert helper.flow.created_entry is None
    assert helper.flow.last_form["errors"] == {
        "volume_homepods_max": "out_of_range",
        "volume_night_offset": "out_of_range",
    }


@_run
async def test_volume_card_rejects_garbage_with_invalid_number():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    result = await helper.async_step_volume({"volume_active_min": "loud"})
    assert helper.flow.created_entry is None
    assert helper.flow.last_form["errors"] == {"volume_active_min": "invalid_number"}


@_run
async def test_volume_card_blank_keeps_stored_value():
    entry = _entry(options={"volume_homepods_media_base": 0.55})
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    result = await helper.async_step_volume({"volume_homepods_media_base": ""})
    assert result["type"] == "create_entry"
    assert result["data"]["volume_homepods_media_base"] == 0.55
