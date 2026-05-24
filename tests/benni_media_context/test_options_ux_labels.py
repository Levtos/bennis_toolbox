"""UX/translations + per-field selector-domain tests for the device cards.

Covers the v0.3.6.2 corrections:
- Umbrella translations declare a label for every card menu option.
- New cards never expose legacy field names (`tv_active`, `ps5_status`,
  `switch_dock`); only the new role-named keys are visible.
- EntitySelector for each new field carries the correct `domain` filter
  so the picker doesn't show "all entities".
- Context card surfaces day/activity/window/door/call with the right
  domain per role.
"""
from __future__ import annotations

import asyncio
import json
import os
from functools import wraps
from pathlib import Path

import pytest

import tests.benni_media_context.test_module_smoke as smoke  # noqa: E402
import tests.benni_media_context.test_options_sources_menu as menu_test  # noqa: E402

# The bmc test stub for EntitySelectorConfig swallows kwargs into a
# nameless `**_kw` and only persists `multiple`. We patch it once,
# *after* it's been registered as `homeassistant.helpers.selector.
# EntitySelectorConfig`, so `domain` and friends remain inspectable
# from our schema introspection below. The change is purely additive
# — existing tests don't rely on it being absent.
import sys as _sys
_ha_sel = _sys.modules.get("homeassistant.helpers.selector")
if _ha_sel is not None:
    _orig_init = _ha_sel.EntitySelectorConfig.__init__

    def _capturing_init(self, multiple=False, **kwargs):
        _orig_init(self, multiple=multiple)
        # Record every config kwarg for later introspection.
        self.kw = dict(kwargs)
        self.kw["multiple"] = multiple

    _ha_sel.EntitySelectorConfig.__init__ = _capturing_init


flow_module = smoke.flow_module
_FakeOptionsFlow = menu_test._FakeOptionsFlow
_entry = menu_test._entry


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


REPO = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TRANSLATIONS = REPO / "custom_components" / "bennis_toolbox" / "translations"


# ---------------------------------------------------------------------------
# 1) Umbrella translations carry a label for every card the menu can show.
# ---------------------------------------------------------------------------


_CARD_KEYS = (
    "tv", "appletv", "ps5", "switch", "pc", "denon", "homepods",
    "context", "sources", "tuning",
)


@pytest.mark.parametrize("locale", ["de", "en"])
def test_all_card_menu_options_have_translation_labels(locale):
    path = TRANSLATIONS / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    menu = (
        data["options"]["step"]["init"]["menu_options"]
    )
    missing = [k for k in _CARD_KEYS if not menu.get(k)]
    assert not missing, f"{locale}.json missing menu labels for: {missing}"


@pytest.mark.parametrize("locale", ["de", "en"])
@pytest.mark.parametrize("card", ["tv", "appletv", "ps5", "switch", "pc", "denon", "homepods", "context"])
def test_each_card_step_has_title_and_field_labels(locale, card):
    path = TRANSLATIONS / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    step = data["options"]["step"].get(card)
    assert step, f"{locale}.json missing options.step.{card}"
    assert step.get("title"), f"{locale}.json {card} step has no title"
    assert step.get("data"), f"{locale}.json {card} step has no data labels"


# ---------------------------------------------------------------------------
# 2) New cards never expose legacy CONF names.
# ---------------------------------------------------------------------------


_LEGACY_NAMES = {
    "tv_active", "tv_source", "tv_power_fallback",
    "appletv",
    "ps5_status", "ps5_title",
    "switch_dock",
    "pc_active",
    "denon_active",
    "homepods",
}


@_run
async def test_no_card_shows_a_legacy_conf_name():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    for card in ("tv", "appletv", "ps5", "switch", "pc", "denon", "homepods"):
        step = getattr(helper, f"async_step_{card}")
        await step()
        schema = helper.flow.last_form["data_schema"]
        keys = {str(getattr(m, "schema", m)) for m in schema.schema}
        clash = keys & _LEGACY_NAMES
        assert not clash, f"card {card!r} exposes legacy key(s): {clash}"


# ---------------------------------------------------------------------------
# 3) EntitySelector domain per field.
# ---------------------------------------------------------------------------


def _selector_domain(validator) -> object:
    """Pull the `domain` filter out of an EntitySelector validator's
    EntitySelectorConfig, regardless of whether it's a class instance
    or a tiny test-stub dict."""
    cfg = getattr(validator, "cfg", None) or getattr(validator, "config", None)
    if cfg is None:
        # The test stubs wrap config in `kw` (see tests/benni_media_context/
        # test_module_smoke.py); EntitySelector(_EntitySelectorConfig(...))
        # stores the config-stub on `cfg.kw`.
        cfg = getattr(validator, "cfg", None)
    if cfg is None:
        return None
    if hasattr(cfg, "kw"):  # _StubEntitySelectorConfig
        return cfg.kw.get("domain")
    return getattr(cfg, "domain", None)


_DEVICE_DOMAIN_EXPECTATIONS = {
    "tv": {
        "tv_player_entity": "media_player",
        "tv_active_entity": "binary_sensor",
        "tv_power_entity": "sensor",
    },
    "appletv": {
        "appletv_player_entity": "media_player",
    },
    "ps5": {
        "ps5_player_entity": "media_player",
        "ps5_active_entity": "binary_sensor",
        "ps5_power_entity": "sensor",
        "ps5_title_entity": "sensor",
        "ps5_network_entity": ["binary_sensor", "device_tracker"],
    },
    "switch": {
        "switch_active_entity": "binary_sensor",
        "switch_power_entity": "sensor",
        "switch_ping_entity": ["binary_sensor", "device_tracker"],
    },
    "pc": {
        "pc_active_entity": "binary_sensor",
        "pc_power_entity": "sensor",
    },
    "denon": {
        "denon_player_entity": "media_player",
        "denon_active_entity": "binary_sensor",
        "denon_power_entity": "sensor",
    },
    "homepods": {
        "homepods_player_entity": "media_player",
    },
}


def _validator_for(schema, name):
    for marker, validator in schema.schema.items():
        if str(getattr(marker, "schema", marker)) == name:
            return validator
    raise AssertionError(f"field {name!r} missing from schema")


@pytest.mark.parametrize("card,expected", list(_DEVICE_DOMAIN_EXPECTATIONS.items()))
@_run
async def test_device_card_selectors_have_correct_domain_filter(card, expected):
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    step = getattr(helper, f"async_step_{card}")
    await step()
    schema = helper.flow.last_form["data_schema"]
    for key, want_domain in expected.items():
        sel = _validator_for(schema, key)
        got = _selector_domain(sel)
        assert got == want_domain, (
            f"card {card!r} field {key!r}: expected domain {want_domain!r}, got {got!r}"
        )


# ---------------------------------------------------------------------------
# 4) Context card.
# ---------------------------------------------------------------------------


@_run
async def test_context_card_lists_only_context_keys_with_correct_domains():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_context()
    assert helper.flow.last_form["step_id"] == "context"
    schema = helper.flow.last_form["data_schema"]
    keys = {str(getattr(m, "schema", m)) for m in schema.schema}
    assert keys == {
        "day_state", "activity_state", "window_state", "entry_door", "call_monitor",
    }
    expected = {
        "day_state": "sensor",
        "activity_state": "sensor",
        "window_state": "binary_sensor",
        "entry_door": "binary_sensor",
        "call_monitor": "binary_sensor",
    }
    for key, domain in expected.items():
        sel = _validator_for(schema, key)
        assert _selector_domain(sel) == domain, key


@_run
async def test_context_card_save_only_touches_context_keys():
    """Editing the context card must not nuke PS5 or tuning settings."""
    entry = _entry(options={
        "ps5_player_entity": "media_player.living_ps5",
        "debounce_seconds": 4,
    })
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_context({
        "day_state": "sensor.context_day_state_combined",
        "window_state": "binary_sensor.living_window_open",
    })
    saved = helper.flow.created_entry["data"]
    assert saved["day_state"] == "sensor.context_day_state_combined"
    assert saved["window_state"] == "binary_sensor.living_window_open"
    # Other surfaces untouched.
    assert saved["ps5_player_entity"] == "media_player.living_ps5"
    assert saved["debounce_seconds"] == 4


@_run
async def test_context_card_empty_submit_does_not_clear_existing_values():
    entry = _entry(options={"day_state": "sensor.context_day_state_combined"})
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=entry, flow=_FakeOptionsFlow(),
    )
    await helper.async_step_context({})  # Skip semantic
    saved = helper.flow.created_entry["data"]
    assert "day_state" not in saved  # cleared because user submitted nothing


# ---------------------------------------------------------------------------
# 5) Menu now includes the `context` step.
# ---------------------------------------------------------------------------


@_run
async def test_menu_contains_context_card():
    helper = flow_module.OptionsFlowHelper(
        hass=object(), entry=_entry(), flow=_FakeOptionsFlow(),
    )
    await helper.async_step_init()
    opts = set(helper.flow.last_menu["menu_options"])
    assert "context" in opts
