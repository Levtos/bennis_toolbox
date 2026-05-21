"""Config- und Options-Flow für Stash HA.

Eine Instanz pro Stash-Server: unique_id ist der GraphQL-Endpoint (URL).
Mehrere Server sind erlaubt; der gleiche Server wird aber nicht doppelt
hinzugefügt.

Add-Flow (1 Schritt `module_step`): URL + optionaler API-Key + optionaler
Player-Name + Poll-Intervall + Webhook-Flag + NSFW-Mode. Validierung über
`StashClient.validate()` (kurze GraphQL-Query auf `version`).
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client, selector

from ...const import CONF_MODULE_ID
from .client import StashClient, StashError
from .const import (
    CONF_API_KEY,
    CONF_NSFW_MODE,
    CONF_PLAYER_NAME,
    CONF_POLL_INTERVAL,
    CONF_URL,
    CONF_USE_WEBHOOK,
    DEFAULT_NSFW_MODE,
    DEFAULT_PLAYER_NAME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_USE_WEBHOOK,
    MODULE_ID,
    NAME,
    NSFW_MODES,
)

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_URL, default=d.get(CONF_URL, "")): str,
        vol.Optional(CONF_API_KEY, default=d.get(CONF_API_KEY, "")): str,
        vol.Optional(CONF_PLAYER_NAME, default=d.get(CONF_PLAYER_NAME, DEFAULT_PLAYER_NAME)): str,
        vol.Optional(CONF_POLL_INTERVAL, default=d.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)):
            vol.All(int, vol.Range(min=2, max=300)),
        vol.Optional(CONF_USE_WEBHOOK, default=d.get(CONF_USE_WEBHOOK, DEFAULT_USE_WEBHOOK)): bool,
        vol.Optional(CONF_NSFW_MODE, default=d.get(CONF_NSFW_MODE, DEFAULT_NSFW_MODE)):
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=NSFW_MODES,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
    })


def _options_schema(opts: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_PLAYER_NAME, default=opts.get(CONF_PLAYER_NAME, DEFAULT_PLAYER_NAME)): str,
        vol.Optional(CONF_POLL_INTERVAL, default=opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)):
            vol.All(int, vol.Range(min=2, max=300)),
        vol.Optional(CONF_USE_WEBHOOK, default=opts.get(CONF_USE_WEBHOOK, DEFAULT_USE_WEBHOOK)): bool,
        vol.Optional(CONF_NSFW_MODE, default=opts.get(CONF_NSFW_MODE, DEFAULT_NSFW_MODE)):
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=NSFW_MODES,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
    })


def _normalised_url(raw_url: str) -> str:
    """Append `/graphql` if missing — that is the only endpoint Stash exposes."""
    url = (raw_url or "").strip().rstrip("/")
    if not url:
        return url
    if not url.endswith("/graphql"):
        url = f"{url}/graphql"
    return url


# ---------------------------------------------------------------------------
# ConfigFlowHelper
# ---------------------------------------------------------------------------


class ConfigFlowHelper:
    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow

    async def async_step_init(self) -> FlowResult:
        return self.flow.async_show_form(
            step_id="module_step", data_schema=_user_schema(),
        )

    async def async_step_module_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_user_schema(),
            )

        url = _normalised_url(user_input.get(CONF_URL, ""))
        if not url:
            return self.flow.async_show_form(
                step_id="module_step",
                data_schema=_user_schema(user_input),
                errors={CONF_URL: "invalid_url"},
            )

        # One config entry per unique Stash endpoint.
        await self.flow.async_set_unique_id(f"{MODULE_ID}:{url}")
        self.flow._abort_if_unique_id_configured()

        api_key = user_input.get(CONF_API_KEY, "") or ""
        session = aiohttp_client.async_get_clientsession(self.hass)
        client = StashClient(url, session, api_key)
        try:
            await client.validate()
        except StashError as err:
            _LOGGER.warning("Stash validate() failed for %s: %s", url, err)
            return self.flow.async_show_form(
                step_id="module_step",
                data_schema=_user_schema(user_input),
                errors={"base": "cannot_connect"},
            )
        except Exception:  # noqa: BLE001
            return self.flow.async_show_form(
                step_id="module_step",
                data_schema=_user_schema(user_input),
                errors={"base": "cannot_connect"},
            )

        title = f"Stash @ {url}"
        data = {
            CONF_MODULE_ID: MODULE_ID,
            CONF_URL: url,
            CONF_API_KEY: api_key,
        }
        options = {
            CONF_PLAYER_NAME: user_input.get(CONF_PLAYER_NAME, DEFAULT_PLAYER_NAME),
            CONF_POLL_INTERVAL: int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)),
            CONF_USE_WEBHOOK: bool(user_input.get(CONF_USE_WEBHOOK, DEFAULT_USE_WEBHOOK)),
            CONF_NSFW_MODE: user_input.get(CONF_NSFW_MODE, DEFAULT_NSFW_MODE),
        }
        return self.flow.async_create_entry(title=title, data=data, options=options)


# ---------------------------------------------------------------------------
# OptionsFlowHelper
# ---------------------------------------------------------------------------


class OptionsFlowHelper:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.flow.async_create_entry(title="", data=user_input)
        return self.flow.async_show_form(
            step_id="init", data_schema=_options_schema(self.entry.options),
        )
