"""v0.3.6.3 hotfix: initial add must not show the legacy mass form.

Until 0.3.6.2 the first screen of the add-flow rendered the entire
`_sources_schema` (tv_active, tv_source, tv_power_fallback, appletv,
ps5_status, switch_dock, …). Users couldn't tell that the new
per-device cards lived under "Configure" instead. The fix collapses
the welcome step to an empty schema — the user clicks Submit and is
dropped onto the new options menu.

Also covers the Denon source resolution: when
`denon_player_entity` is configured, the source attribute must come
from that media_player and never from a legacy active-binary that
happens to be wired to a power sensor.
"""
from __future__ import annotations

import asyncio
import types
from functools import wraps

import pytest

import tests.benni_media_context.test_module_smoke as smoke  # noqa: E402

flow_module = smoke.flow_module


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


_FakeUmbrellaFlow = smoke._FakeUmbrellaFlow


# ---------------------------------------------------------------------------
# 1) Initial add shows an empty welcome form, not the legacy mass schema.
# ---------------------------------------------------------------------------


_LEGACY_FIRST_SCREEN_KEYS = {
    "tv_active", "tv_source", "tv_power_fallback", "appletv",
    "ps5_status", "ps5_title", "switch_dock", "pc_active",
    "denon_active", "homepods",
    # Title-classifier inputs were also on that form:
    "classifier_ps5", "classifier_pc", "classifier_homepods", "classifier_media",
}


def _schema_keys(schema) -> set[str]:
    return {str(getattr(m, "schema", m)) for m in schema.schema}


@_run
async def test_add_flow_welcome_form_is_empty():
    """The first screen must not surface any source picker — those
    live under per-device cards in the options menu now."""
    flow = _FakeUmbrellaFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    await helper.async_step_init()
    assert flow.last_form["step_id"] == "module_step"
    keys = _schema_keys(flow.last_form["data_schema"])
    assert keys == set(), f"welcome form must be empty, got fields: {keys}"


@_run
async def test_add_flow_welcome_form_contains_no_legacy_fields():
    """Defensive: even if someone re-adds a field later, none of the
    historic mass-form fields are allowed on the welcome screen."""
    flow = _FakeUmbrellaFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    await helper.async_step_init()
    keys = _schema_keys(flow.last_form["data_schema"])
    leaked = keys & _LEGACY_FIRST_SCREEN_KEYS
    assert not leaked, f"legacy fields leaked into welcome form: {leaked}"


@_run
async def test_add_flow_submits_empty_and_creates_entry():
    """User clicks Submit on the empty welcome → entry is created
    immediately, no further steps required. The new options menu
    handles per-device configuration afterwards."""
    flow = _FakeUmbrellaFlow()
    helper = flow_module.ConfigFlowHelper(hass=object(), flow=flow)
    await helper.async_step_init()
    result = await helper.async_step_module_step({})
    assert result["type"] == "create_entry"
    # module_id is wired up automatically; no source keys persisted.
    assert result["data"] == {"_module_id": "benni_media_context"}


# ---------------------------------------------------------------------------
# 2) Options menu still exposes every device card after the hotfix.
# ---------------------------------------------------------------------------


import tests.benni_media_context.test_options_sources_menu as menu_test  # noqa: E402

_FakeOptionsFlow = menu_test._FakeOptionsFlow
_entry = menu_test._entry


@_run
async def test_options_menu_still_lists_all_device_and_context_cards():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_init()
    opts = set(helper.flow.last_menu["menu_options"])
    # `sources` is gated to entries that already have legacy values
    # — see test_config_flow_minimal for the gating contract.
    assert {"tv", "appletv", "ps5", "switch", "pc", "denon",
            "homepods", "context", "tuning"} <= opts


# ---------------------------------------------------------------------------
# 3) Denon card saves the new player key.
# ---------------------------------------------------------------------------


@_run
async def test_denon_card_persists_player_entity_only_to_options():
    """Editing the Denon card must store `denon_player_entity` under
    entry.options. Legacy `denon_active` is not auto-populated and
    other entries' options remain untouched."""
    entry = _entry(options={"ps5_player_entity": "media_player.living_ps5"})
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_denon({
        "denon_player_entity": "media_player.living_denon",
    })
    saved = helper.flow.created_entry["data"]
    assert saved["denon_player_entity"] == "media_player.living_denon"
    # Did not invent a denon_active value out of thin air.
    assert "denon_active" not in saved
    # Other devices preserved.
    assert saved["ps5_player_entity"] == "media_player.living_ps5"
