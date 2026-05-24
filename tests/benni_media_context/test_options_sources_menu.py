"""Options-Flow für Benni Media Context bietet Sources + Tuning.

Bis 0.3.5.5 zeigte das Gear-Icon nur die Volume-/Debounce-Knöpfe; die
Medienquellen liessen sich nach dem Anlegen nicht mehr ändern. Diese
Tests pinnen das neue Menü plus den Sources-Step.
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


class _FakeOptionsFlow:
    """Captures form/menu/create-entry calls for the OptionsFlowHelper."""

    def __init__(self) -> None:
        self.last_form: dict | None = None
        self.last_menu: dict | None = None
        self.created_entry: dict | None = None

    def async_show_form(self, step_id, data_schema=None, **_kw):
        self.last_form = {"step_id": step_id, "data_schema": data_schema}
        return {"type": "form", "step_id": step_id}

    def async_show_menu(self, step_id, menu_options=None):
        self.last_menu = {"step_id": step_id, "menu_options": list(menu_options or [])}
        return {"type": "menu", "step_id": step_id}

    def async_create_entry(self, title, data, options=None):
        self.created_entry = {
            "title": title, "data": dict(data),
            "options": dict(options or {}),
        }
        return self.created_entry

    def async_abort(self, reason):
        return {"type": "abort", "reason": reason}


def _entry(data=None, options=None):
    return types.SimpleNamespace(
        data=dict(data or {}),
        options=dict(options or {}),
        entry_id="bmc-entry",
    )


# ---------------------------------------------------------------------------
# 1) Menu.
# ---------------------------------------------------------------------------


@_run
async def test_options_init_shows_menu_with_sources_and_tuning():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    result = await helper.async_step_init()
    assert result["type"] == "menu"
    opts = set(helper.flow.last_menu["menu_options"])
    # Per-device cards plus the tuning step are always present. The
    # legacy aggregate `sources` step is now gated to entries with
    # legacy values — this entry has none, so it shouldn't appear.
    assert {"tv", "appletv", "ps5", "switch", "pc", "denon", "homepods", "tuning"} <= opts
    assert "sources" not in opts


# ---------------------------------------------------------------------------
# 2) Sources step renders the media-source schema seeded with the merged
#    data + options, and writes the result back to options.
# ---------------------------------------------------------------------------


@_run
async def test_sources_step_renders_with_existing_data_as_defaults():
    helper = flow_module.OptionsFlowHelper(
        hass=object(),
        entry=_entry(data={
            "tv_active": "binary_sensor.tv_active_legacy",
            "homepods": ["media_player.homepod_living"],
        }),
        flow=_FakeOptionsFlow(),
    )
    await helper.async_step_sources()
    schema = helper.flow.last_form["data_schema"]
    # The form schema must list the media-source fields, with the
    # legacy values surviving as defaults.
    keys = {str(getattr(m, "schema", m)) for m in schema.schema}
    assert "tv_active" in keys
    assert "homepods" in keys
    assert "appletv" in keys  # rendered even when empty
    for marker in schema.schema:
        if str(getattr(marker, "schema", marker)) == "tv_active":
            assert marker.default() == "binary_sensor.tv_active_legacy"
        if str(getattr(marker, "schema", marker)) == "homepods":
            assert marker.default() == ["media_player.homepod_living"]


@_run
async def test_sources_step_persists_user_input_to_options():
    """Saving in the sources step writes to entry.options, not data —
    that's what HA's OptionsFlow does, and the coordinator's merge
    behaviour ensures the new values take precedence on the next read.
    """
    helper = flow_module.OptionsFlowHelper(
        hass=object(),
        entry=_entry(
            data={"tv_active": "binary_sensor.tv_active_legacy"},
            options={"debounce_seconds": 4},
        ),
        flow=_FakeOptionsFlow(),
    )
    result = await helper.async_step_sources({
        "tv_active": "binary_sensor.tv_active_new",
        "appletv": "media_player.apple_tv",
    })
    assert result["title"] == ""
    saved = helper.flow.created_entry["data"]
    # New source overrides legacy on read via the coordinator's merge.
    assert saved["tv_active"] == "binary_sensor.tv_active_new"
    assert saved["appletv"] == "media_player.apple_tv"
    # Tuning options are preserved across a sources-only edit.
    assert saved["debounce_seconds"] == 4


@_run
async def test_sources_step_drops_empty_fields_so_data_fallback_works():
    """If the user clears a slot (selects "no entity"), the resulting
    entry.options must NOT carry a None/empty value — otherwise the
    coordinator's merge would mask the legacy data-side fallback."""
    helper = flow_module.OptionsFlowHelper(
        hass=object(),
        entry=_entry(data={"tv_active": "binary_sensor.tv_legacy"}),
        flow=_FakeOptionsFlow(),
    )
    result = await helper.async_step_sources({
        "tv_active": None,
        "appletv": "",
        "homepods": [],
    })
    saved = helper.flow.created_entry["data"]
    assert "tv_active" not in saved
    assert "appletv" not in saved
    assert "homepods" not in saved


# ---------------------------------------------------------------------------
# 3) Tuning step continues to work and saves volume/debounce knobs.
# ---------------------------------------------------------------------------


@_run
async def test_tuning_step_persists_volume_values():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(),
        flow=_FakeOptionsFlow(),
    )
    await helper.async_step_tuning()  # show form first
    result = await helper.async_step_tuning({
        "debounce_seconds": 4,
        "quiet_ducking_level": 0.15,
        "base_volume_homepods": 0.35,
        "base_volume_denon": 0.4,
        "track_boost_offset": 0.1,
        "window_volume_offset": -0.05,
    })
    saved = helper.flow.created_entry["data"]
    assert saved["debounce_seconds"] == 4
    assert saved["base_volume_homepods"] == 0.35
    assert saved["window_volume_offset"] == -0.05


@_run
async def test_tuning_step_preserves_source_options_already_set():
    helper = flow_module.OptionsFlowHelper(
        hass=object(),
        entry=_entry(options={
            "tv_active": "binary_sensor.tv_active_via_options",
        }),
        flow=_FakeOptionsFlow(),
    )
    result = await helper.async_step_tuning({
        "debounce_seconds": 5,
    })
    saved = helper.flow.created_entry["data"]
    # Tuning edit must not blow away source overrides stored on options.
    assert saved["tv_active"] == "binary_sensor.tv_active_via_options"
    assert saved["debounce_seconds"] == 5
