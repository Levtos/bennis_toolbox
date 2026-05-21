"""Config- und Options-Flow für die Toolbox.

UI-Konzept:

  Geräte & Dienste -> "Benni's Toolbox hinzufügen"
    Step 1 (user):     Modul auswählen
    Step 2 (<module>): Modulspezifische Konfiguration

Jede Modulinstanz wird zu einem eigenen Config-Entry mit Domain
`bennis_toolbox` und `data[_module_id] = "<module_id>"`. Mehrere Instanzen
desselben Moduls sind möglich, sofern das Modul es erlaubt (Default: ja).
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import CONF_MODULE_ID, DOMAIN
from .modules import REGISTERED_MODULE_IDS, get_spec, load_module, selectable_specs
from .modules.base import ModuleStatus

_LOGGER = logging.getLogger(__name__)


class BennisToolboxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._module_id: str | None = None
        self._helper: Any | None = None  # module-spezifische FlowHelper-Instanz

    # --- Step: Modul auswählen ------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        specs = await self.hass.async_add_executor_job(selectable_specs)
        options = [
            selector.SelectOptionDict(value=s.module_id, label=f"{s.name} ({s.status.value})")
            for s in specs
        ]
        schema = vol.Schema({
            vol.Required(CONF_MODULE_ID): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        })

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=schema)

        module_id = user_input[CONF_MODULE_ID]
        if module_id not in REGISTERED_MODULE_IDS:
            return self.async_show_form(
                step_id="user", data_schema=schema, errors={"base": "unknown_module"}
            )

        spec = await self.hass.async_add_executor_job(get_spec, module_id)
        if spec.status in (ModuleStatus.PENDING, ModuleStatus.STUB):
            # Erstelle trotzdem einen Entry, damit der Nutzer das Modul
            # vormerken kann; Setup ist no-op (siehe __init__.async_setup_entry).
            return self.async_create_entry(
                title=f"{spec.name} (Vorschau)",
                data={CONF_MODULE_ID: module_id},
            )

        self._module_id = module_id
        self._helper = await _maybe_make_helper(self.hass, module_id, self)
        return await self._dispatch_first_step()

    # --- Step: an Modul-Helper delegieren ------------------------------------

    async def _dispatch_first_step(self) -> FlowResult:
        assert self._module_id and self._helper
        return await self._helper.async_step_init()

    # Generischer Hop für mehrstufige Modul-Flows. Modulhelfer dürfen
    # `flow.async_show_form(step_id="<beliebig>", …)` zurückgeben und
    # implementieren das passende `async_step_<beliebig>` selbst — wir
    # leiten unbekannte Step-Methoden an den Helper durch. Das
    # kanonische Eingangs-Step heißt aus Lesbarkeit `module_step`.
    async def async_step_module_step(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._delegate_step("module_step", user_input)

    async def _delegate_step(self, step_id: str, user_input):
        if self._helper is None:
            return self.async_abort(reason="invalid_flow_state")
        handler = getattr(self._helper, f"async_step_{step_id}", None)
        if handler is None:
            return self.async_abort(reason="invalid_flow_state")
        return await handler(user_input)

    def __getattr__(self, name: str):
        # Nur Step-Methoden weiterleiten, die HA via getattr() auflöst.
        # __getattr__ wird nur bei nicht gefundenen Attributen aufgerufen,
        # nicht bei explizit definierten Methoden.
        if name.startswith("async_step_"):
            step_id = name[len("async_step_"):]

            async def _proxy(user_input=None, _sid=step_id):
                return await self._delegate_step(_sid, user_input)

            return _proxy
        raise AttributeError(name)

    # --- Options Flow ---------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BennisToolboxOptionsFlow(config_entry)


class BennisToolboxOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry
        self._helper: Any | None = None

    async def _ensure_helper(self):
        if self._helper is not None:
            return True
        module_id: str | None = self.config_entry.data.get(CONF_MODULE_ID)
        if not module_id:
            return False
        try:
            mod = await self.hass.async_add_executor_job(load_module, module_id)
        except Exception:  # noqa: BLE001
            return False
        helper_cls = getattr(mod, "OptionsFlowHelper", None)
        if helper_cls is None:
            return False
        self._helper = helper_cls(self.hass, self.config_entry, self)
        return True

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if not await self._ensure_helper():
            module_id: str | None = self.config_entry.data.get(CONF_MODULE_ID)
            if not module_id:
                return self.async_abort(reason="missing_module")
            # Modul ohne OptionsFlowHelper — keine Options.
            return self.async_create_entry(title="", data=dict(self.config_entry.options))
        return await self._helper.async_step_init(user_input)

    def __getattr__(self, name: str):
        if name.startswith("async_step_"):
            step_id = name[len("async_step_"):]

            async def _proxy(user_input=None, _sid=step_id):
                if not await self._ensure_helper():
                    return self.async_abort(reason="invalid_flow_state")
                handler = getattr(self._helper, f"async_step_{_sid}", None)
                if handler is None:
                    return self.async_abort(reason="invalid_flow_state")
                return await handler(user_input)

            return _proxy
        raise AttributeError(name)


async def _maybe_make_helper(hass, module_id: str, flow):
    """Modul-spezifischen Flow-Helfer instantiieren, falls vorhanden."""
    mod = await hass.async_add_executor_job(load_module, module_id)
    helper_cls = getattr(mod, "ConfigFlowHelper", None)
    if helper_cls is None:
        spec = await hass.async_add_executor_job(get_spec, module_id)
        # Fallback: leerer Entry, das Modul hat nichts zu konfigurieren.
        class _Empty:
            async def async_step_init(self_inner) -> FlowResult:
                return flow.async_create_entry(
                    title=spec.name,
                    data={CONF_MODULE_ID: module_id},
                )
        return _Empty()
    return helper_cls(hass, flow)
