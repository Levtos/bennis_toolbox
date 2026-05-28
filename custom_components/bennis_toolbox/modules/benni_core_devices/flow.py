"""Config- und Options-Flow für Benni Core · Devices.

Multi-Instance — eine Config-Entry pro Device.
Unique-ID: `benni_core_devices:<slug>`.

Config-Flow:
1. `pick_mode` — Menü: einzelnes Gerät vs. Bulk-Import (YAML)
2a. single → `module_step` (Typ wählen) → `slots` (Slots + Runtime)
2b. bulk   → `bulk` (YAML-Liste) → feuert pro Device einen SOURCE_IMPORT-Flow

Options-Flow (Menü):
- `slots`    — Slot-Entities ändern
- `runtime`  — Threshold, Sticky-Hold, Watt-Buckets, Sekundär-Sensoren
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
import yaml
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ...const import CONF_MODULE_ID, DOMAIN
from .const import (
    CONF_BULK_YAML,
    CONF_DEVICE_TYPE,
    CONF_DISPLAY_NAME,
    CONF_EXPOSE_SECONDARY_SENSORS,
    CONF_SLUG,
    CONF_STICKY_HOLD_SECONDS,
    CONF_WATT_BUCKETS,
    CONF_WATT_THRESHOLD_ON,
    DEFAULT_EXPOSE_SECONDARY_SENSORS,
    DEFAULT_STICKY_HOLD_SECONDS,
    DEFAULT_WATT_THRESHOLD_ON,
    DEVICE_TYPE_SLUGS,
    MODULE_ID,
    DeviceType,
)
from .device_types import (
    is_valid_slug,
    profile_for,
    validate_import_device,
    validate_import_payload,
)


def _build_entry_data(
    device_type: DeviceType, slug: str, src: dict[str, Any]
) -> dict[str, Any]:
    """Baut entry.data aus Slot-Quelle (Config-Flow ODER Import)."""
    data: dict[str, Any] = {
        CONF_MODULE_ID: MODULE_ID,
        CONF_DEVICE_TYPE: device_type.value,
        CONF_SLUG: slug,
        CONF_DISPLAY_NAME: src.get(CONF_DISPLAY_NAME) or slug,
    }
    for slot in profile_for(device_type).slots:
        v = src.get(slot.key)
        if v:
            data[slot.key] = v
    return data


def _build_entry_options(
    src: dict[str, Any], buckets: list[Any]
) -> dict[str, Any]:
    """Baut entry.options aus Slot-Quelle (Config-Flow ODER Import)."""
    return {
        CONF_WATT_THRESHOLD_ON: int(
            src.get(CONF_WATT_THRESHOLD_ON, DEFAULT_WATT_THRESHOLD_ON)
        ),
        CONF_STICKY_HOLD_SECONDS: int(
            src.get(CONF_STICKY_HOLD_SECONDS, DEFAULT_STICKY_HOLD_SECONDS)
        ),
        CONF_EXPOSE_SECONDARY_SENSORS: bool(
            src.get(CONF_EXPOSE_SECONDARY_SENSORS, DEFAULT_EXPOSE_SECONDARY_SENSORS)
        ),
        CONF_WATT_BUCKETS: buckets or [],
    }


def _esel(domains: tuple[str, ...]) -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=list(domains), multiple=False)
    )


def _slot_schema(
    device_type: DeviceType, defaults: dict[str, Any] | None = None
) -> vol.Schema:
    """Schema mit allen Slots des Typs + Runtime-Knöpfe."""
    d = defaults or {}
    profile = profile_for(device_type)
    fields: dict[Any, Any] = {
        vol.Required(CONF_SLUG, default=d.get(CONF_SLUG, "")): str,
        vol.Required(CONF_DISPLAY_NAME, default=d.get(CONF_DISPLAY_NAME, "")): str,
    }
    for slot in profile.slots:
        marker_cls = vol.Required if slot.required else vol.Optional
        default = d.get(slot.key)
        if default:
            marker = marker_cls(slot.key, default=default)
        elif slot.required:
            marker = marker_cls(slot.key)
        else:
            marker = marker_cls(slot.key)
        fields[marker] = _esel(slot.domains)
    # Runtime-Knöpfe
    fields[vol.Optional(
        CONF_WATT_THRESHOLD_ON,
        default=d.get(CONF_WATT_THRESHOLD_ON, DEFAULT_WATT_THRESHOLD_ON),
    )] = vol.All(int, vol.Range(min=0, max=5000))
    fields[vol.Optional(
        CONF_STICKY_HOLD_SECONDS,
        default=d.get(CONF_STICKY_HOLD_SECONDS, DEFAULT_STICKY_HOLD_SECONDS),
    )] = vol.All(int, vol.Range(min=0, max=3600))
    fields[vol.Optional(
        CONF_EXPOSE_SECONDARY_SENSORS,
        default=d.get(CONF_EXPOSE_SECONDARY_SENSORS, DEFAULT_EXPOSE_SECONDARY_SENSORS),
    )] = bool
    fields[vol.Optional(
        CONF_WATT_BUCKETS, default=d.get(CONF_WATT_BUCKETS, "")
    )] = selector.TextSelector(
        selector.TextSelectorConfig(multiline=True)
    )
    return vol.Schema(fields)


def _bulk_schema(default: str = "") -> vol.Schema:
    """Schema für den Bulk-Import: eine YAML-Liste von Device-Definitionen."""
    return vol.Schema(
        {
            vol.Required(CONF_BULK_YAML, default=default): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
    )


def _type_step_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_DEVICE_TYPE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(DEVICE_TYPE_SLUGS),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _validate_slug(slug: str) -> str | None:
    if not is_valid_slug(slug):
        return "invalid_slug"
    return None


def _parse_buckets_yaml(raw: str) -> tuple[Any, str | None]:
    """Parse Watt-Buckets aus YAML-Text. Returns (parsed, error_key)."""
    if not raw or not raw.strip():
        return ([], None)
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError:
        return (None, "invalid_yaml")
    if parsed is None:
        return ([], None)
    if not isinstance(parsed, list):
        return (None, "buckets_not_list")
    for entry in parsed:
        if not isinstance(entry, dict) or "state" not in entry:
            return (None, "bucket_missing_state")
    return (parsed, None)


# ─────────────────────────────────────────────────────────────────────────────
# ConfigFlowHelper
# ─────────────────────────────────────────────────────────────────────────────


class ConfigFlowHelper:
    """Wird vom zentralen BennisToolboxConfigFlow aufgerufen."""

    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow
        self._chosen_type: DeviceType | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        # Menü: einzelnes Gerät vs. Bulk-Import (YAML).
        return self.flow.async_show_menu(
            step_id="pick_mode", menu_options=["single", "bulk"]
        )

    # ── Modus "Einzelnes Gerät" ──────────────────────────────────────────────

    async def async_step_single(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.flow.async_show_form(
            step_id="module_step", data_schema=_type_step_schema()
        )

    # ── Modus "Bulk-Import (YAML)" ───────────────────────────────────────────

    async def async_step_bulk(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="bulk", data_schema=_bulk_schema()
            )

        raw = user_input.get(CONF_BULK_YAML, "")
        try:
            parsed = yaml.safe_load(raw) if raw and raw.strip() else None
        except yaml.YAMLError:
            return self.flow.async_show_form(
                step_id="bulk",
                data_schema=_bulk_schema(raw),
                errors={CONF_BULK_YAML: "invalid_yaml"},
            )

        valid, errors = validate_import_payload(parsed)
        if errors:
            return self.flow.async_show_form(
                step_id="bulk",
                data_schema=_bulk_schema(raw),
                errors={CONF_BULK_YAML: "bulk_invalid"},
                description_placeholders={"errors": "\n".join(errors)},
            )

        # Pro Device einen SOURCE_IMPORT-Flow feuern → async_step_import →
        # async_import → eigener Config-Entry. Hintergrund-Tasks, damit der
        # aktuelle Flow sauber mit einer Info-Abort-Meldung endet.
        for d in valid:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data={CONF_MODULE_ID: MODULE_ID, **d},
                )
            )
        return self.flow.async_abort(reason="bulk_import_started")

    async def async_step_module_step(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        # Schritt 1: Typ wählen
        if user_input is None or (
            self._chosen_type is None and CONF_DEVICE_TYPE not in user_input
        ):
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_type_step_schema()
            )

        if self._chosen_type is None:
            try:
                self._chosen_type = DeviceType(user_input[CONF_DEVICE_TYPE])
            except ValueError:
                return self.flow.async_show_form(
                    step_id="module_step",
                    data_schema=_type_step_schema(),
                    errors={CONF_DEVICE_TYPE: "invalid_type"},
                )
            return self.flow.async_show_form(
                step_id="slots", data_schema=_slot_schema(self._chosen_type)
            )

        # Schritt 2: Slots ausgefüllt
        return await self.async_step_slots(user_input)

    async def async_step_slots(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None or self._chosen_type is None:
            return self.flow.async_show_form(
                step_id="slots",
                data_schema=_slot_schema(self._chosen_type or DeviceType.PLUG),
            )

        errors: dict[str, str] = {}
        slug = str(user_input.get(CONF_SLUG, "")).strip().lower()
        slug_err = _validate_slug(slug)
        if slug_err:
            errors[CONF_SLUG] = slug_err

        buckets_raw = user_input.get(CONF_WATT_BUCKETS, "")
        buckets, bucket_err = _parse_buckets_yaml(buckets_raw)
        if bucket_err:
            errors[CONF_WATT_BUCKETS] = bucket_err

        profile = profile_for(self._chosen_type)
        for slot in profile.slots:
            if slot.required and not user_input.get(slot.key):
                errors[slot.key] = "required"

        if errors:
            return self.flow.async_show_form(
                step_id="slots",
                data_schema=_slot_schema(self._chosen_type, user_input),
                errors=errors,
            )

        await self.flow.async_set_unique_id(f"{MODULE_ID}:{slug}")
        self.flow._abort_if_unique_id_configured()

        data = _build_entry_data(self._chosen_type, slug, user_input)
        options = _build_entry_options(user_input, buckets)
        return self.flow.async_create_entry(
            title=data[CONF_DISPLAY_NAME] or slug, data=data, options=options
        )

    # --- Bulk-Import (R-DC-08) — pro Device ein SOURCE_IMPORT-Flow -----------

    async def async_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Legt EIN Device aus validierten Import-Daten an.

        Erwartet ein bereits durch validate_import_payload geprüftes Dict
        (slug normalisiert, Pflicht-Slots vorhanden). Defensive Re-Validierung
        hier nochmal, falls direkt aufgerufen.
        """
        err = validate_import_device(import_data)
        if err:
            return self.flow.async_abort(reason="import_invalid")
        device_type = DeviceType(import_data[CONF_DEVICE_TYPE])
        slug = str(import_data[CONF_SLUG]).strip().lower()

        await self.flow.async_set_unique_id(f"{MODULE_ID}:{slug}")
        self.flow._abort_if_unique_id_configured()

        data = _build_entry_data(device_type, slug, import_data)
        buckets, _ = (import_data.get(CONF_WATT_BUCKETS) or [], None)
        # Import liefert Buckets bereits als Liste (nicht YAML-Text)
        if isinstance(buckets, str):
            buckets, _err = _parse_buckets_yaml(buckets)
            buckets = buckets or []
        options = _build_entry_options(import_data, buckets)
        return self.flow.async_create_entry(
            title=data[CONF_DISPLAY_NAME] or slug, data=data, options=options
        )


# ─────────────────────────────────────────────────────────────────────────────
# OptionsFlowHelper
# ─────────────────────────────────────────────────────────────────────────────


class OptionsFlowHelper:
    """Erlaubt nachträgliches Anpassen aller Slots + Runtime."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow

    @property
    def device_type(self) -> DeviceType:
        return DeviceType(self.entry.data[CONF_DEVICE_TYPE])

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="init", menu_options=["slots", "runtime"]
        )

    async def async_step_slots(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        profile = profile_for(self.device_type)
        if user_input is not None:
            errors: dict[str, str] = {}
            for slot in profile.slots:
                if slot.required and not user_input.get(slot.key):
                    errors[slot.key] = "required"
            if errors:
                return self.flow.async_show_form(
                    step_id="slots",
                    data_schema=_slot_schema(self.device_type, {**self.entry.data, **user_input}),
                    errors=errors,
                )
            new_data = dict(self.entry.data)
            for slot in profile.slots:
                v = user_input.get(slot.key)
                if v:
                    new_data[slot.key] = v
                else:
                    new_data.pop(slot.key, None)
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.flow.async_create_entry(title="", data=self.entry.options)
        # slug+display kommen aus data — Slot-Schema bietet sie aber an;
        # wir reuse das Schema, der User editiert dort nur Slots.
        defaults = {**self.entry.data}
        return self.flow.async_show_form(
            step_id="slots", data_schema=_slot_schema(self.device_type, defaults)
        )

    async def async_step_runtime(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            errors: dict[str, str] = {}
            buckets_raw = user_input.get(CONF_WATT_BUCKETS, "")
            buckets, err = _parse_buckets_yaml(buckets_raw)
            if err:
                errors[CONF_WATT_BUCKETS] = err
            if errors:
                return self.flow.async_show_form(
                    step_id="runtime",
                    data_schema=_runtime_schema({**self.entry.options, **user_input}),
                    errors=errors,
                )
            new_options = {
                **self.entry.options,
                CONF_WATT_THRESHOLD_ON: int(
                    user_input.get(CONF_WATT_THRESHOLD_ON, DEFAULT_WATT_THRESHOLD_ON)
                ),
                CONF_STICKY_HOLD_SECONDS: int(
                    user_input.get(CONF_STICKY_HOLD_SECONDS, DEFAULT_STICKY_HOLD_SECONDS)
                ),
                CONF_EXPOSE_SECONDARY_SENSORS: bool(
                    user_input.get(
                        CONF_EXPOSE_SECONDARY_SENSORS, DEFAULT_EXPOSE_SECONDARY_SENSORS
                    )
                ),
                CONF_WATT_BUCKETS: buckets or [],
            }
            return self.flow.async_create_entry(title="", data=new_options)
        return self.flow.async_show_form(
            step_id="runtime", data_schema=_runtime_schema(self.entry.options)
        )


def _runtime_schema(opts: dict[str, Any]) -> vol.Schema:
    buckets_default = opts.get(CONF_WATT_BUCKETS)
    if isinstance(buckets_default, list):
        try:
            buckets_default = yaml.safe_dump(buckets_default, sort_keys=False).strip()
        except Exception:  # noqa: BLE001
            buckets_default = ""
    elif not isinstance(buckets_default, str):
        buckets_default = ""
    return vol.Schema(
        {
            vol.Optional(
                CONF_WATT_THRESHOLD_ON,
                default=opts.get(CONF_WATT_THRESHOLD_ON, DEFAULT_WATT_THRESHOLD_ON),
            ): vol.All(int, vol.Range(min=0, max=5000)),
            vol.Optional(
                CONF_STICKY_HOLD_SECONDS,
                default=opts.get(CONF_STICKY_HOLD_SECONDS, DEFAULT_STICKY_HOLD_SECONDS),
            ): vol.All(int, vol.Range(min=0, max=3600)),
            vol.Optional(
                CONF_EXPOSE_SECONDARY_SENSORS,
                default=opts.get(
                    CONF_EXPOSE_SECONDARY_SENSORS, DEFAULT_EXPOSE_SECONDARY_SENSORS
                ),
            ): bool,
            vol.Optional(CONF_WATT_BUCKETS, default=buckets_default): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
    )
