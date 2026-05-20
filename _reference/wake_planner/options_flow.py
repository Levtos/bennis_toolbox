"""Options flow for Wake Planner — calendars + holiday defaults only.

People and rules are managed in the Wake Planner sidebar panel.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries

from .config_flow import (
    CALENDAR_OPTION_KEYS,
    SPECIAL_RULE_OPTION_KEYS,
    _calendar_schema,
    _clean_calendar_input,
    _clean_special_rules_input,
    _special_rules_schema,
)

_LOGGER = logging.getLogger(__name__)


class WakePlannerOptionsFlow(config_entries.OptionsFlow):
    """Edit Wake Planner global options."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        entry = self.config_entry
        self._options = {**entry.data, **entry.options}
        self._initialized = True

    def _entity_ids(self, domain: str) -> list[str]:
        try:
            return sorted(self.hass.states.async_entity_ids(domain))
        except Exception:  # noqa: BLE001
            return []

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        self._ensure_initialized()
        return await self.async_step_calendar(user_input)

    async def async_step_calendar(self, user_input: dict[str, Any] | None = None):
        self._ensure_initialized()
        if user_input is not None:
            for key in CALENDAR_OPTION_KEYS:
                self._options.pop(key, None)
            self._options.update(_clean_calendar_input(user_input))
            return await self.async_step_special_rules()
        return self.async_show_form(
            step_id="calendar",
            data_schema=_calendar_schema(self._entity_ids("calendar"), self._options),
        )

    async def async_step_special_rules(self, user_input: dict[str, Any] | None = None):
        self._ensure_initialized()
        if user_input is not None:
            for key in SPECIAL_RULE_OPTION_KEYS:
                self._options.pop(key, None)
            self._options.update(_clean_special_rules_input(user_input))
            return self.async_create_entry(title="", data=self._options)
        return self.async_show_form(
            step_id="special_rules",
            data_schema=_special_rules_schema(self._options),
        )
