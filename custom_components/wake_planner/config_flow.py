"""Config flow for Wake Planner — minimal setup, real config happens in the panel."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CALENDAR_ENTITY_ID,
    CONF_HOLIDAY_BEHAVIOR,
    CONF_HOLIDAY_CALENDAR_ENTITY_ID,
    CONF_MANUAL_HOLIDAY_DATES,
    CONF_PERSONS,
    DOMAIN,
    HOLIDAY_SKIP,
    HOLIDAY_WEEKEND_PROFILE,
)

_LOGGER = logging.getLogger(__name__)

CALENDAR_OPTION_KEYS = {
    CONF_CALENDAR_ENTITY_ID,
    CONF_HOLIDAY_CALENDAR_ENTITY_ID,
}
SPECIAL_RULE_OPTION_KEYS = {
    CONF_HOLIDAY_BEHAVIOR,
    CONF_MANUAL_HOLIDAY_DATES,
}


class WakePlannerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Minimal setup: optional calendars; people + rules are added in the panel."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        from .options_flow import WakePlannerOptionsFlow

        return WakePlannerOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        if user_input is not None:
            data = {CONF_PERSONS: []}
            data.update(_clean_calendar_input(user_input))
            return self.async_create_entry(title="Wake Planner", data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=_calendar_schema(self._entity_ids("calendar")),
        )

    def _entity_ids(self, domain: str) -> list[str]:
        try:
            return sorted(self.hass.states.async_entity_ids(domain))
        except Exception:  # noqa: BLE001
            return []


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
                translation_key="holiday_behavior",
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
