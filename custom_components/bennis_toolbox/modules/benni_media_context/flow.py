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
    CONF_BIO_STATE,
    CONF_BOOST_OFFSET,
    CONF_CALL_MONITOR,
    CONF_DAY_STATE,
    CONF_DEBOUNCE,
    CONF_DENON_ACTIVE,
    CONF_DOOR,
    CONF_HOMEPODS,
    CONF_MANUAL_PLAYBACK,
    CONF_MEDIA_STOP_LATCH,
    CONF_OPENING_ANY_OPEN,
    CONF_PC_ACTIVE,
    CONF_PC_GAMING_ACTIVE,
    CONF_PLANNED_RADIO,
    CONF_PS5_STATUS,
    CONF_PS5_TITLE,
    CONF_QUIET_DUCK,
    CONF_QUIET_MODE_ENTITY,
    CONF_SWITCH_DOCK,
    CONF_TITLE_CLASSIFIER_HOMEPODS,
    CONF_TITLE_CLASSIFIER_MEDIA,
    CONF_TITLE_CLASSIFIER_PC,
    CONF_TITLE_CLASSIFIER_PS5,
    CONF_TV_ACTIVE,
    CONF_TV_POWER_FALLBACK,
    CONF_TV_SOURCE,
    CONF_VOL_ACTIVE_MIN,
    CONF_VOL_DENON_BASE,
    CONF_VOL_DENON_MAX,
    CONF_VOL_DUCKED_TARGET,
    CONF_VOL_EDGE_DAY_OFFSET,
    CONF_VOL_HOMEPODS_BASE,
    CONF_VOL_HOMEPODS_MAX,
    CONF_VOL_NIGHT_OFFSET,
    CONF_VOL_OPENING_OFFSET,
    CONF_WINDOW_OFFSET,
    CONF_WINDOW_STATE,
    DEFAULT_BASE_VOL_DENON,
    DEFAULT_BASE_VOL_HOMEPODS,
    DEFAULT_BOOST_OFFSET,
    DEFAULT_DEBOUNCE,
    DEFAULT_QUIET_DUCK,
    DEFAULT_VOL_ACTIVE_MIN,
    DEFAULT_VOL_DENON_BASE,
    DEFAULT_VOL_DENON_MAX,
    DEFAULT_VOL_DUCKED_TARGET,
    DEFAULT_VOL_EDGE_DAY_OFFSET,
    DEFAULT_VOL_HOMEPODS_BASE,
    DEFAULT_VOL_HOMEPODS_MAX,
    DEFAULT_VOL_NIGHT_OFFSET,
    DEFAULT_VOL_OPENING_OFFSET,
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


# HA's NumberSelector renders values in the user's locale → a DE locale
# user sees "0,15" / "-0,1" with a comma decimal separator, which is
# unusual for tuning knobs and confusing when the spec writes the
# values with a dot. We side-step the locale by using a plain text
# input plus dot/comma-tolerant coercion. Both "0.15" and "0,15"
# parse to the same float; we render defaults with a dot.


def _to_decimal(value: Any) -> float:
    """Parse a number or string-decimal into a Python float.

    Accepts both '.' and ',' as decimal separator; strips whitespace;
    treats empty input as 0.0. Raises on anything that doesn't look
    like a number.
    """
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip().replace(",", ".")
    return float(s)


def _text_selector() -> selector.TextSelector:
    """Build the plain-text input used for every tuning field.

    Why not `vol.All(TextSelector, _to_decimal, vol.Range)`? HA renders
    config-flow schemas via `voluptuous_serialize`, which does not
    reliably pick a Selector out of an `vol.All` chain across all HA
    versions (Einhornzentrale's box hit a render error on "Lautstärke
    & Debounce" because of exactly that wrap). The Selector must be
    the bare value; coercion + range validation happen in the step
    handler after submit.
    """
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
    )


# Range bounds per tuning field. Used both by the field-level UI
# (via the tooltip range hint) and by `_validate_tuning_input` to
# reject out-of-range submissions cleanly.
_TUNING_RANGES: dict[str, tuple[float, float]] = {
    CONF_DEBOUNCE: (0.0, 60.0),
    CONF_QUIET_DUCK: (0.0, 1.0),
    CONF_BASE_VOL_HOMEPODS: (0.0, 1.0),
    CONF_BASE_VOL_DENON: (0.0, 1.0),
    CONF_BOOST_OFFSET: (-0.5, 0.5),
    CONF_WINDOW_OFFSET: (-0.5, 0.5),
}


def _validate_tuning_input(
    user_input: dict[str, Any],
) -> tuple[dict[str, float], dict[str, str]]:
    """Parse + range-check a tuning submission.

    Returns ``(cleaned, errors)``. ``cleaned`` only contains keys that
    parsed successfully; ``errors`` maps the failing key to a
    translation-friendly error code ("invalid_number" or
    "out_of_range").
    """
    cleaned: dict[str, float] = {}
    errors: dict[str, str] = {}
    for key, (lo, hi) in _TUNING_RANGES.items():
        raw = user_input.get(key)
        if raw is None or raw == "":
            # Optional field left blank → keep stored value (drop key).
            continue
        try:
            value = _to_decimal(raw)
        except (TypeError, ValueError):
            errors[key] = "invalid_number"
            continue
        if value < lo or value > hi:
            errors[key] = "out_of_range"
            continue
        cleaned[key] = value
    return cleaned, errors


def _fmt_decimal(value: Any, default: float) -> str:
    """Render a stored decimal as a dot-separated string for the form
    default. Falls back to `default` when the stored value is None /
    empty / unparsable."""
    try:
        return f"{float(value)}"
    except (TypeError, ValueError):
        return f"{float(default)}"


_TUNING_DEFAULTS: dict[str, float] = {
    CONF_DEBOUNCE: DEFAULT_DEBOUNCE,
    CONF_QUIET_DUCK: DEFAULT_QUIET_DUCK,
    CONF_BASE_VOL_HOMEPODS: DEFAULT_BASE_VOL_HOMEPODS,
    CONF_BASE_VOL_DENON: DEFAULT_BASE_VOL_DENON,
    CONF_BOOST_OFFSET: DEFAULT_BOOST_OFFSET,
    CONF_WINDOW_OFFSET: DEFAULT_WINDOW_OFFSET,
}


# Orchestrator-specific entity slots (the 0.3.8 contract). Each
# binds an option key to the matching EntitySelector domain so the
# picker stays narrow.
_ORCHESTRATOR_ENTITY_DOMAINS: dict[str, str] = {
    CONF_BIO_STATE: "sensor",
    CONF_MANUAL_PLAYBACK: "binary_sensor",
    CONF_PLANNED_RADIO: "binary_sensor",
    CONF_PC_GAMING_ACTIVE: "binary_sensor",
    CONF_MEDIA_STOP_LATCH: "binary_sensor",
    CONF_OPENING_ANY_OPEN: "binary_sensor",
    CONF_QUIET_MODE_ENTITY: "binary_sensor",
}


def _orchestrator_card_schema(defaults: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for key, domain in _ORCHESTRATOR_ENTITY_DOMAINS.items():
        sel = selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))
        fields[_opt_entity_marker(key, defaults.get(key))] = sel
    return vol.Schema(fields)


# Volume tuning card: the 9 dot-separated decimal fields. Reuses
# the bare-TextSelector pattern from the 0.3.7 tuning fix to dodge
# locale formatting.
_VOLUME_DEFAULTS: dict[str, float] = {
    CONF_VOL_HOMEPODS_BASE: DEFAULT_VOL_HOMEPODS_BASE,
    CONF_VOL_DENON_BASE: DEFAULT_VOL_DENON_BASE,
    CONF_VOL_DUCKED_TARGET: DEFAULT_VOL_DUCKED_TARGET,
    CONF_VOL_HOMEPODS_MAX: DEFAULT_VOL_HOMEPODS_MAX,
    CONF_VOL_DENON_MAX: DEFAULT_VOL_DENON_MAX,
    CONF_VOL_ACTIVE_MIN: DEFAULT_VOL_ACTIVE_MIN,
    CONF_VOL_NIGHT_OFFSET: DEFAULT_VOL_NIGHT_OFFSET,
    CONF_VOL_EDGE_DAY_OFFSET: DEFAULT_VOL_EDGE_DAY_OFFSET,
    CONF_VOL_OPENING_OFFSET: DEFAULT_VOL_OPENING_OFFSET,
}

# Range bounds for the volume tuning fields. Targets/duck stay in
# [0, 1], offsets can swing negative.
_VOLUME_RANGES: dict[str, tuple[float, float]] = {
    CONF_VOL_HOMEPODS_BASE: (0.0, 1.0),
    CONF_VOL_DENON_BASE: (0.0, 1.0),
    CONF_VOL_DUCKED_TARGET: (0.0, 1.0),
    CONF_VOL_HOMEPODS_MAX: (0.0, 1.0),
    CONF_VOL_DENON_MAX: (0.0, 1.0),
    CONF_VOL_ACTIVE_MIN: (0.0, 1.0),
    CONF_VOL_NIGHT_OFFSET: (-0.5, 0.5),
    CONF_VOL_EDGE_DAY_OFFSET: (-0.5, 0.5),
    CONF_VOL_OPENING_OFFSET: (-0.5, 0.5),
}


def _volume_schema(opts: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for key, default in _VOLUME_DEFAULTS.items():
        fields[
            vol.Optional(key, default=_fmt_decimal(opts.get(key), default))
        ] = _text_selector()
    return vol.Schema(fields)


def _validate_volume_input(
    user_input: dict[str, Any],
) -> tuple[dict[str, float], dict[str, str]]:
    """Sibling of `_validate_tuning_input` for the volume card."""
    cleaned: dict[str, float] = {}
    errors: dict[str, str] = {}
    for key, (lo, hi) in _VOLUME_RANGES.items():
        raw = user_input.get(key)
        if raw is None or raw == "":
            continue
        try:
            value = _to_decimal(raw)
        except (TypeError, ValueError):
            errors[key] = "invalid_number"
            continue
        if value < lo or value > hi:
            errors[key] = "out_of_range"
            continue
        cleaned[key] = value
    return cleaned, errors


def _options_schema(opts: dict[str, Any]) -> vol.Schema:
    """Build the tuning schema with bare TextSelectors.

    Each field is a plain `selector.TextSelector` — no `vol.All`
    wrapping, because some HA versions fail to render selectors that
    are nested inside `vol.All`. Coercion + range checks live in
    `_validate_tuning_input` and run in the step handler.
    """
    fields: dict[Any, Any] = {}
    for key, default in _TUNING_DEFAULTS.items():
        fields[
            vol.Optional(key, default=_fmt_decimal(opts.get(key), default))
        ] = _text_selector()
    return vol.Schema(fields)


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

    # All CONF keys that the legacy aggregate `sources` step still
    # exposes. Used to decide whether to offer that step in the menu.
    _LEGACY_SOURCE_CONF_KEYS: tuple[str, ...] = (
        CONF_TV_ACTIVE, CONF_TV_SOURCE, CONF_TV_POWER_FALLBACK, CONF_APPLETV,
        CONF_PS5_STATUS, CONF_PS5_TITLE, CONF_SWITCH_DOCK, CONF_PC_ACTIVE,
        CONF_DENON_ACTIVE, CONF_HOMEPODS,
        CONF_TITLE_CLASSIFIER_PS5, CONF_TITLE_CLASSIFIER_PC,
        CONF_TITLE_CLASSIFIER_HOMEPODS, CONF_TITLE_CLASSIFIER_MEDIA,
        CONF_DOOR, CONF_CALL_MONITOR, CONF_DAY_STATE, CONF_ACTIVITY_STATE,
        CONF_WINDOW_STATE,
    )

    def _has_legacy_values(self) -> bool:
        """Return True if the entry still has anything stored under
        a legacy CONF key in either ``data`` or ``options``."""
        merged = _merged(self.entry)
        for key in self._LEGACY_SOURCE_CONF_KEYS:
            v = merged.get(key)
            if v not in (None, "", [], ()):
                return True
        return False

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        # Per-device cards are the only normal configuration surface.
        # The legacy aggregate "sources" step is now gated: it only
        # appears for entries that already have legacy values stored
        # (existing installs migrating from the old mass form). Fresh
        # entries don't see it at all, removing the foot-gun where
        # opening "Auslöser & Quellen" would dump the old schema.
        menu = [
            "tv", "appletv", "ps5", "switch", "pc", "denon", "homepods",
            "context", "orchestrator", "volume",
        ]
        if self._has_legacy_values():
            menu.append("sources")
        menu.append("tuning")
        return self.flow.async_show_menu(step_id="init", menu_options=menu)

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

    async def async_step_orchestrator(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Orchestrator-specific entity slots (0.3.8).

        Houses the entity pickers that don't belong on a device card:
        bio_state, manual_playback, planned_radio, pc_gaming_active,
        media_stop_latch, opening_any_open, quiet_mode. Same save
        semantics as the device cards — empty fields drop the option
        so legacy data-side values can resurface.
        """
        keys = tuple(_ORCHESTRATOR_ENTITY_DOMAINS.keys())
        if user_input is None:
            return self.flow.async_show_form(
                step_id="orchestrator",
                data_schema=_orchestrator_card_schema(_merged(self.entry)),
            )
        new_opts = dict(self.entry.options)
        cleaned = {k: v for k, v in user_input.items() if v not in (None, "", [])}
        for k in keys:
            if k in cleaned:
                new_opts[k] = cleaned[k]
            else:
                new_opts.pop(k, None)
        new_opts.pop(CONF_MODULE_ID, None)
        return self.flow.async_create_entry(title="", data=new_opts)

    async def async_step_volume(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Volume orchestrator tuning card (0.3.8).

        Holds the 9 dot-separated decimal fields the volume
        orchestrator reads. Validation lives in the step handler
        (same pattern as the legacy tuning fix) so bare TextSelectors
        render reliably across HA versions.
        """
        if user_input is None:
            return self.flow.async_show_form(
                step_id="volume",
                data_schema=_volume_schema(_merged(self.entry)),
            )
        cleaned, errors = _validate_volume_input(user_input)
        if errors:
            merged_for_render = {**_merged(self.entry), **user_input}
            return self.flow.async_show_form(
                step_id="volume",
                data_schema=_volume_schema(merged_for_render),
                errors=errors,
            )
        new_opts = {**self.entry.options, **cleaned}
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
            cleaned, errors = _validate_tuning_input(user_input)
            if errors:
                # Re-render with the values the user typed (so they
                # don't have to retype everything) plus the per-field
                # error codes the frontend can translate.
                merged_for_render = {**_merged(self.entry), **user_input}
                return self.flow.async_show_form(
                    step_id="tuning",
                    data_schema=_options_schema(merged_for_render),
                    errors=errors,
                )
            new_opts = {**self.entry.options, **cleaned}
            new_opts.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=new_opts)
        return self.flow.async_show_form(
            step_id="tuning", data_schema=_options_schema(_merged(self.entry)),
        )
