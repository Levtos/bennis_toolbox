"""Config- und Options-Flow-Helfer des Wake-Planner-Moduls.

Werden vom Umbrella-Flow (`bennis_toolbox.config_flow`) instanziert. Sie
registrieren *keine* eigene HA-Domain — die einzige Flow-Registrierung
läuft über die Umbrella.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ...const import CONF_MODULE_ID
from .const import (
    CONF_CALENDAR_ENTITY_ID,
    CONF_HOLIDAY_BEHAVIOR,
    CONF_HOLIDAY_CALENDAR_ENTITY_ID,
    CONF_MANUAL_HOLIDAY_DATES,
    CONF_PERSONS,
    HOLIDAY_SKIP,
    HOLIDAY_WEEKEND_PROFILE,
    MODULE_ID,
    NAME,
)

_LOGGER = logging.getLogger(__name__)

CALENDAR_OPTION_KEYS = {CONF_CALENDAR_ENTITY_ID, CONF_HOLIDAY_CALENDAR_ENTITY_ID}
SPECIAL_RULE_OPTION_KEYS = {CONF_HOLIDAY_BEHAVIOR, CONF_MANUAL_HOLIDAY_DATES}


def _is_empty(value: Any) -> bool:
    return value is None or value in ("", [], {})


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    return {key: (None if _is_empty(value) else value) for key, value in data.items()}


def _entity_select(entity_ids: list[str] | None, current: str | None = None) -> selector.SelectSelector:
    options = [{"value": "", "label": "—"}]
    pool = set(entity_ids or [])
    if current:
        pool.add(current)
    options.extend({"value": e, "label": e} for e in sorted(pool))
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
    )


def _calendar_schema(entity_ids: list[str] | None = None, defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    cal = defaults.get(CONF_CALENDAR_ENTITY_ID)
    hol = defaults.get(CONF_HOLIDAY_CALENDAR_ENTITY_ID)
    return vol.Schema({
        vol.Optional(CONF_CALENDAR_ENTITY_ID, default=cal or ""): _entity_select(entity_ids, cal),
        vol.Optional(CONF_HOLIDAY_CALENDAR_ENTITY_ID, default=hol or ""): _entity_select(entity_ids, hol),
    })


def _special_rules_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(
            CONF_HOLIDAY_BEHAVIOR, default=defaults.get(CONF_HOLIDAY_BEHAVIOR, HOLIDAY_SKIP)
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[HOLIDAY_SKIP, HOLIDAY_WEEKEND_PROFILE],
                translation_key="wake_planner_holiday_behavior",
            )
        ),
        vol.Optional(
            CONF_MANUAL_HOLIDAY_DATES, default=defaults.get(CONF_MANUAL_HOLIDAY_DATES) or ""
        ): selector.TextSelector(),
    })


def _clean_calendar_input(user_input: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize(user_input)
    return {k: v for k, v in normalized.items() if k in CALENDAR_OPTION_KEYS and v is not None}


def _clean_special_rules_input(user_input: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize(user_input)
    return {
        k: (v.strip() if isinstance(v, str) else v)
        for k, v in normalized.items()
        if k in SPECIAL_RULE_OPTION_KEYS and v is not None
    }


def _calendar_entity_ids(hass: HomeAssistant) -> list[str]:
    try:
        return sorted(hass.states.async_entity_ids("calendar"))
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# ConfigFlowHelper
# ---------------------------------------------------------------------------


class ConfigFlowHelper:
    """Minimal-Setup im Add-Flow: optionale Kalender.

    Personen + Regeln werden später im Wake-Planner-Sidebar-Panel verwaltet.
    """

    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow  # umbrella ConfigFlow instance

    async def async_step_init(self) -> FlowResult:
        return self.flow.async_show_form(
            step_id="module_step",
            data_schema=_calendar_schema(_calendar_entity_ids(self.hass)),
        )

    async def async_step_module_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step",
                data_schema=_calendar_schema(_calendar_entity_ids(self.hass)),
            )
        data: dict[str, Any] = {
            CONF_MODULE_ID: MODULE_ID,
            CONF_PERSONS: [],
        }
        data.update(_clean_calendar_input(user_input))
        return self.flow.async_create_entry(title=NAME, data=data)


# ---------------------------------------------------------------------------
# OptionsFlowHelper
# ---------------------------------------------------------------------------


class OptionsFlowHelper:
    """Editiert globale Wake-Planner-Optionen (Kalender + Holiday-Defaults)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow
        self._options: dict[str, Any] = {**entry.data, **entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_calendar(user_input)

    async def async_step_calendar(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            for key in CALENDAR_OPTION_KEYS:
                self._options.pop(key, None)
            self._options.update(_clean_calendar_input(user_input))
            return await self.async_step_special_rules()
        return self.flow.async_show_form(
            step_id="calendar",
            data_schema=_calendar_schema(_calendar_entity_ids(self.hass), self._options),
        )

    async def async_step_special_rules(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            for key in SPECIAL_RULE_OPTION_KEYS:
                self._options.pop(key, None)
            self._options.update(_clean_special_rules_input(user_input))
            # Module-ID nicht in Options speichern; sie bleibt in entry.data.
            self._options.pop(CONF_MODULE_ID, None)
            return self.flow.async_create_entry(title="", data=self._options)
        return self.flow.async_show_form(
            step_id="special_rules",
            data_schema=_special_rules_schema(self._options),
        )
