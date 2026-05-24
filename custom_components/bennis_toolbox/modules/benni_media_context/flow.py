"""Config- und Options-Flow-Helfer für Benni Media Context.

Single-Instance über unique_id `benni_media_context_singleton`.

Add-Flow (1 Schritt):
  module_step — alle Quell-Entities sind optional.

Options-Flow (1 Schritt):
  init — Volumen/Debounce-Parameter.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ...const import CONF_MODULE_ID
from .const import (
    CONF_ACTIVITY_STATE,
    CONF_APPLETV,
    CONF_BASE_VOL_DENON,
    CONF_BASE_VOL_HOMEPODS,
    CONF_BOOST_OFFSET,
    CONF_CALL_MONITOR,
    CONF_DAY_STATE,
    CONF_DEBOUNCE,
    CONF_DENON_ACTIVE,
    CONF_DOOR,
    CONF_HOMEPODS,
    CONF_PC_ACTIVE,
    CONF_PS5_STATUS,
    CONF_PS5_TITLE,
    CONF_QUIET_DUCK,
    CONF_SWITCH_DOCK,
    CONF_TITLE_CLASSIFIER_HOMEPODS,
    CONF_TITLE_CLASSIFIER_MEDIA,
    CONF_TITLE_CLASSIFIER_PC,
    CONF_TITLE_CLASSIFIER_PS5,
    CONF_TV_ACTIVE,
    CONF_TV_POWER_FALLBACK,
    CONF_TV_SOURCE,
    CONF_WINDOW_OFFSET,
    CONF_WINDOW_STATE,
    DEFAULT_BASE_VOL_DENON,
    DEFAULT_BASE_VOL_HOMEPODS,
    DEFAULT_BOOST_OFFSET,
    DEFAULT_DEBOUNCE,
    DEFAULT_QUIET_DUCK,
    DEFAULT_WINDOW_OFFSET,
    DEVICE_CARDS,
    MODULE_ID,
    NAME,
)

_ENTITY = selector.EntitySelector(selector.EntitySelectorConfig())
_ENTITY_MULTI = selector.EntitySelector(selector.EntitySelectorConfig(multiple=True))


def _sources_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}

    def _opt(key: str, sel):
        marker = vol.Optional(key, default=d[key]) if d.get(key) else vol.Optional(key)
        return marker, sel

    fields: dict[Any, Any] = {}
    for k in (
        CONF_TV_ACTIVE, CONF_TV_SOURCE, CONF_TV_POWER_FALLBACK, CONF_APPLETV,
        CONF_PS5_STATUS, CONF_PS5_TITLE, CONF_SWITCH_DOCK, CONF_PC_ACTIVE,
        CONF_DENON_ACTIVE,
    ):
        m, s = _opt(k, _ENTITY)
        fields[m] = s
    m, s = _opt(CONF_HOMEPODS, _ENTITY_MULTI)
    fields[m] = s
    for k in (
        CONF_TITLE_CLASSIFIER_PS5, CONF_TITLE_CLASSIFIER_PC,
        CONF_TITLE_CLASSIFIER_HOMEPODS, CONF_TITLE_CLASSIFIER_MEDIA,
        CONF_DOOR, CONF_CALL_MONITOR, CONF_DAY_STATE, CONF_ACTIVITY_STATE,
        CONF_WINDOW_STATE,
    ):
        m, s = _opt(k, _ENTITY)
        fields[m] = s
    return vol.Schema(fields)


def _number(min_: float, max_: float, step: float = 0.01) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_, max=max_, step=step, mode=selector.NumberSelectorMode.BOX
        )
    )


def _options_schema(opts: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_DEBOUNCE, default=opts.get(CONF_DEBOUNCE, DEFAULT_DEBOUNCE)):
            _number(0, 60, 0.5),
        vol.Optional(CONF_QUIET_DUCK, default=opts.get(CONF_QUIET_DUCK, DEFAULT_QUIET_DUCK)):
            _number(0, 1, 0.01),
        vol.Optional(CONF_BASE_VOL_HOMEPODS, default=opts.get(CONF_BASE_VOL_HOMEPODS, DEFAULT_BASE_VOL_HOMEPODS)):
            _number(0, 1, 0.01),
        vol.Optional(CONF_BASE_VOL_DENON, default=opts.get(CONF_BASE_VOL_DENON, DEFAULT_BASE_VOL_DENON)):
            _number(0, 1, 0.01),
        vol.Optional(CONF_BOOST_OFFSET, default=opts.get(CONF_BOOST_OFFSET, DEFAULT_BOOST_OFFSET)):
            _number(-0.5, 0.5, 0.01),
        vol.Optional(CONF_WINDOW_OFFSET, default=opts.get(CONF_WINDOW_OFFSET, DEFAULT_WINDOW_OFFSET)):
            _number(-0.5, 0.5, 0.01),
    })


# ---------------------------------------------------------------------------
# ConfigFlowHelper
# ---------------------------------------------------------------------------


# Minimal welcome schema for the initial add — no source pickers,
# no legacy fields. After creation, sources are picked per-device
# from the options menu under "Configure".
_WELCOME_SCHEMA = vol.Schema({})


class ConfigFlowHelper:
    """Initial add-flow.

    Until 0.3.6.2 the first screen dumped the entire legacy source
    schema (`tv_active`, `ps5_status`, `switch_dock`, …) into the
    user's face — a confusing way to start, and inconsistent with
    the new per-device cards that appear under "Configure". This
    flow now creates an empty entry immediately so the user can
    head straight to the device cards. Legacy values can still be
    edited through the legacy "Auslöser & Quellen" step that
    remains in the options menu.
    """

    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow

    async def async_step_init(self) -> FlowResult:
        await self.flow.async_set_unique_id(f"{MODULE_ID}_singleton")
        self.flow._abort_if_unique_id_configured()
        return self.flow.async_show_form(
            step_id="module_step", data_schema=_WELCOME_SCHEMA,
        )

    async def async_step_module_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_WELCOME_SCHEMA,
            )
        # The welcome form has no fields; any keys that arrive here
        # (e.g. from older add-flow callers that still pass legacy
        # values) are preserved on entry.data for the legacy-
        # compatible read path in the coordinator.
        data: dict[str, Any] = {CONF_MODULE_ID: MODULE_ID}
        data.update({k: v for k, v in user_input.items() if v not in (None, "", [])})
        return self.flow.async_create_entry(title=NAME, data=data)


# ---------------------------------------------------------------------------
# OptionsFlowHelper
# ---------------------------------------------------------------------------


def _merged(entry: ConfigEntry) -> dict[str, Any]:
    """Defaults seen by edit forms: options win over original data."""
    merged = dict(entry.data)
    merged.update(entry.options)
    merged.pop(CONF_MODULE_ID, None)
    return merged


def _opt_entity_marker(key: str, default: Any):
    """Build an Optional marker that omits None/"" defaults — HA's
    EntitySelector rejects None as a value."""
    if default in (None, "", []):
        return vol.Optional(key)
    return vol.Optional(key, default=default)


# ---------------------------------------------------------------------------
# Per-field EntitySelector domain mapping for the device cards.
#
# Each CONF key gets its own EntitySelector with a tight `domain` filter
# so the picker only offers entities of the right kind (no more "all
# entities" picker). The role suffix in the key name drives the mapping:
# `*_player_entity` → media_player, `*_active_entity` → binary_sensor,
# `*_power_entity` / `*_title_entity` → sensor, ping/network → both
# binary_sensor and device_tracker.
# ---------------------------------------------------------------------------


def _entity_selector_for(key: str) -> selector.EntitySelector:
    """Return an EntitySelector with the correct domain filter."""
    if key.endswith("_player_entity"):
        domains: Any = "media_player"
    elif key.endswith("_active_entity"):
        domains = "binary_sensor"
    elif key.endswith("_power_entity") or key.endswith("_title_entity"):
        domains = "sensor"
    elif key.endswith("_ping_entity") or key.endswith("_network_entity"):
        domains = ["binary_sensor", "device_tracker"]
    else:
        # Context globals fall through to a sensible default — see
        # `_context_globals_card_schema` for the per-context overrides.
        domains = None
    cfg = selector.EntitySelectorConfig(domain=domains) if domains else selector.EntitySelectorConfig()
    return selector.EntitySelector(cfg)


def _device_card_schema(card: str, defaults: dict[str, Any]) -> vol.Schema:
    """Render the per-device card as a small voluptuous schema.

    Each field gets a domain-filtered selector so the user only picks
    entities that make sense (media_player for the *_player_entity
    slots, binary_sensor for *_active_entity, …). The card only shows
    keys that belong to this device; the OptionsFlow merges them on
    save so unrelated keys keep their values (the "Skip" semantics
    from v0.3.6 fall out naturally: closing the dialog without
    visiting a card writes nothing).
    """
    fields: dict[Any, Any] = {}
    for key in DEVICE_CARDS[card]:
        fields[_opt_entity_marker(key, defaults.get(key))] = _entity_selector_for(key)
    return vol.Schema(fields)


# Context globals card — exposes day/activity/window/door/call slots
# with the right domain filter, alongside the device cards.
_CONTEXT_GLOBALS_KEYS: tuple[str, ...] = (
    "day_state",
    "activity_state",
    "window_state",
    "entry_door",
    "call_monitor",
)


def _context_globals_card_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Schema for the new "Context / globale Quellen" card."""
    fields: dict[Any, Any] = {}
    sensor_domains = {"day_state": "sensor", "activity_state": "sensor"}
    binary_domains = {
        "window_state": "binary_sensor",
        "entry_door": "binary_sensor",
        "call_monitor": "binary_sensor",
    }
    for key in _CONTEXT_GLOBALS_KEYS:
        domain = sensor_domains.get(key) or binary_domains.get(key)
        sel = selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))
        fields[_opt_entity_marker(key, defaults.get(key))] = sel
    return vol.Schema(fields)


# Keys that the per-device cards manage. Used to wipe stale options
# entries when the user clears a slot on save.
_ALL_DEVICE_KEYS: set[str] = {k for keys in DEVICE_CARDS.values() for k in keys}


class OptionsFlowHelper:
    """Two-step options menu.

    The 0.3.5.4 build only exposed the volume/debounce tuning. Users
    couldn't change media sources after the initial add — every fix
    required deleting and re-adding the entry. The new menu surfaces
    both surfaces explicitly: ``sources`` for media-related entities,
    ``tuning`` for the volume/debounce knobs.

    Source values are stored in ``entry.options`` from here on (the
    coordinator now reads merged options-over-data, so legacy entries
    keep working without migration).
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="init",
            menu_options=[
                "tv", "appletv", "ps5", "switch", "pc", "denon", "homepods",
                "context", "sources", "tuning",
            ],
        )

    # ---- Per-device cards --------------------------------------------------

    async def _save_card(self, card: str, user_input: dict[str, Any]) -> FlowResult:
        """Merge a per-card submit into entry.options.

        Only the keys declared for this card are touched. Keys the user
        cleared get removed from options so the coordinator's merge can
        fall back to entry.data. Other devices' keys stay untouched.
        """
        new_opts = dict(self.entry.options)
        card_keys = set(DEVICE_CARDS[card])
        cleaned = {k: v for k, v in user_input.items() if v not in (None, "", [])}
        for k in card_keys:
            if k in cleaned:
                new_opts[k] = cleaned[k]
            else:
                # User cleared the slot in this card → drop from options
                # so any legacy data-side value resurfaces. If the slot
                # wasn't in options before, this is a no-op.
                new_opts.pop(k, None)
        new_opts.pop(CONF_MODULE_ID, None)
        return self.flow.async_create_entry(title="", data=new_opts)

    async def _show_card(self, card: str) -> FlowResult:
        return self.flow.async_show_form(
            step_id=card,
            data_schema=_device_card_schema(card, _merged(self.entry)),
        )

    async def async_step_tv(self, user_input=None) -> FlowResult:
        if user_input is None:
            return await self._show_card("tv")
        return await self._save_card("tv", user_input)

    async def async_step_appletv(self, user_input=None) -> FlowResult:
        if user_input is None:
            return await self._show_card("appletv")
        return await self._save_card("appletv", user_input)

    async def async_step_ps5(self, user_input=None) -> FlowResult:
        if user_input is None:
            return await self._show_card("ps5")
        return await self._save_card("ps5", user_input)

    async def async_step_switch(self, user_input=None) -> FlowResult:
        if user_input is None:
            return await self._show_card("switch")
        return await self._save_card("switch", user_input)

    async def async_step_pc(self, user_input=None) -> FlowResult:
        if user_input is None:
            return await self._show_card("pc")
        return await self._save_card("pc", user_input)

    async def async_step_denon(self, user_input=None) -> FlowResult:
        if user_input is None:
            return await self._show_card("denon")
        return await self._save_card("denon", user_input)

    async def async_step_homepods(self, user_input=None) -> FlowResult:
        if user_input is None:
            return await self._show_card("homepods")
        return await self._save_card("homepods", user_input)

    async def async_step_context(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Context-globals card: day phase / activity / window / door / call.

        Behaves like a device card — only the listed CONF keys are
        touched on save. Domain-filtered selectors apply per field.
        """
        if user_input is None:
            return self.flow.async_show_form(
                step_id="context",
                data_schema=_context_globals_card_schema(_merged(self.entry)),
            )
        new_opts = dict(self.entry.options)
        cleaned = {k: v for k, v in user_input.items() if v not in (None, "", [])}
        for k in _CONTEXT_GLOBALS_KEYS:
            if k in cleaned:
                new_opts[k] = cleaned[k]
            else:
                new_opts.pop(k, None)
        new_opts.pop(CONF_MODULE_ID, None)
        return self.flow.async_create_entry(title="", data=new_opts)

    async def async_step_sources(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            # Drop empty slots so the coordinator's merge keeps falling
            # back to entry.data for keys the user cleared.
            cleaned = {k: v for k, v in user_input.items() if v not in (None, "", [])}
            new_opts = {**self.entry.options}
            # Wipe any source key the user *omitted* from the form (HA
            # only submits the keys present in the schema) so legacy
            # data-side values surface again instead of being overridden
            # by stale options.
            for k in cleaned:
                new_opts[k] = cleaned[k]
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(
            step_id="sources", data_schema=_sources_schema(_merged(self.entry)),
        )

    async def async_step_tuning(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            new_opts = {**self.entry.options, **user_input}
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(
            step_id="tuning", data_schema=_options_schema(_merged(self.entry)),
        )
