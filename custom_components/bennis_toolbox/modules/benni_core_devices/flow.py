"""Config- und Options-Flow für Benni Core · Devices (Feld-Masken-Modell).

Multi-Instance — eine Config-Entry pro Device. Unique-ID: `benni_core_devices:<slug>`.

Config-Flow:
1. `pick_mode` — Menü: einzelnes Gerät vs. Bulk-Import (YAML)
2a. single → `module_step` (Typ) → `fields` (Maske + Runtime + Watt-Zeilen)
              → `slots` (Entity-Picker je gewähltem Feld, Pflicht)
2b. bulk   → `bulk` (YAML-Liste) → SOURCE_IMPORT-Flow je Device

Der `device_type` steuert nur die Attribut-Semantik + Default-Feldauswahl.
Welche Felder belegt werden, wählt der User frei (Feld-Maske). Gewählte
Felder werden zu Pflicht-Pickern.

Options-Flow (Menü): `fields` (Maske→Picker) | `runtime` (Knöpfe+Watt-Zeilen).
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
    CONF_FIELDS,
    CONF_SLUG,
    CONF_STICKY_HOLD_SECONDS,
    CONF_WATT_BUCKETS,
    CONF_WATT_IDLE_OP,
    CONF_WATT_IDLE_VALUE,
    CONF_WATT_OFF_OP,
    CONF_WATT_OFF_VALUE,
    CONF_WATT_PLAYING_OP,
    CONF_WATT_PLAYING_VALUE,
    CONF_WATT_THRESHOLD_ON,
    DEFAULT_EXPOSE_SECONDARY_SENSORS,
    DEFAULT_STICKY_HOLD_SECONDS,
    DEFAULT_WATT_THRESHOLD_ON,
    DEVICE_TYPE_SLUGS,
    MODULE_ID,
    WATT_OPERATOR_CHOICES,
    DeviceType,
)
from .device_types import (
    ALL_SLOT_KEYS,
    SLOT_CATALOG,
    default_fields,
    is_valid_slug,
    profile_for,
    validate_import_device,
    validate_import_payload,
)

# Reihenfolge der Watt-Bucket-Zeilen (state-name → op-key, value-key)
_WATT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("off", CONF_WATT_OFF_OP, CONF_WATT_OFF_VALUE),
    ("idle", CONF_WATT_IDLE_OP, CONF_WATT_IDLE_VALUE),
    ("playing", CONF_WATT_PLAYING_OP, CONF_WATT_PLAYING_VALUE),
)


# ─────────────────────────────────────────────────────────────────────────────
# Schema-Bausteine
# ─────────────────────────────────────────────────────────────────────────────


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


def _bulk_schema(default: str = "") -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_BULK_YAML, default=default): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
    )


def _operator_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(WATT_OPERATOR_CHOICES),
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _fields_schema(device_type: DeviceType, defaults: dict[str, Any]) -> vol.Schema:
    """Maske: slug, display, Feld-Multiselect, Runtime-Knöpfe, Watt-Zeilen."""
    pre = defaults.get(CONF_FIELDS) or list(default_fields(device_type))
    fields: dict[Any, Any] = {
        vol.Required(CONF_SLUG, default=defaults.get(CONF_SLUG, "")): str,
        vol.Required(CONF_DISPLAY_NAME, default=defaults.get(CONF_DISPLAY_NAME, "")): str,
        vol.Required(CONF_FIELDS, default=pre): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(ALL_SLOT_KEYS),
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Optional(
            CONF_WATT_THRESHOLD_ON,
            default=defaults.get(CONF_WATT_THRESHOLD_ON, DEFAULT_WATT_THRESHOLD_ON),
        ): vol.All(int, vol.Range(min=0, max=5000)),
        vol.Optional(
            CONF_STICKY_HOLD_SECONDS,
            default=defaults.get(CONF_STICKY_HOLD_SECONDS, DEFAULT_STICKY_HOLD_SECONDS),
        ): vol.All(int, vol.Range(min=0, max=3600)),
        vol.Optional(
            CONF_EXPOSE_SECONDARY_SENSORS,
            default=defaults.get(
                CONF_EXPOSE_SECONDARY_SENSORS, DEFAULT_EXPOSE_SECONDARY_SENSORS
            ),
        ): bool,
    }
    # Watt-Zeilen: pro Zeile Operator (optional) + Wert (optional)
    for _state, op_key, val_key in _WATT_ROWS:
        op_default = defaults.get(op_key)
        if op_default:
            fields[vol.Optional(op_key, default=op_default)] = _operator_selector()
        else:
            fields[vol.Optional(op_key)] = _operator_selector()
        fields[vol.Optional(val_key, default=defaults.get(val_key))] = vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=10000))
        )
    return vol.Schema(fields)


def _slots_schema(field_keys: list[str], defaults: dict[str, Any]) -> vol.Schema:
    """Entity-Picker je gewähltem Feld (Pflicht), breite Domains aus Katalog."""
    fields: dict[Any, Any] = {}
    for key in field_keys:
        spec = SLOT_CATALOG.get(key)
        if spec is None:
            continue
        sel = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=list(spec.domains), multiple=False)
        )
        default = defaults.get(key)
        if default:
            fields[vol.Required(key, default=default)] = sel
        else:
            fields[vol.Required(key)] = sel
    return vol.Schema(fields)


# ─────────────────────────────────────────────────────────────────────────────
# Watt-Bucket-Konvertierung (Form ↔ Liste)
# ─────────────────────────────────────────────────────────────────────────────


def _buckets_from_form(src: dict[str, Any]) -> list[dict[str, Any]]:
    """Baut die Bucket-Liste aus den 6 Watt-Form-Feldern.

    Eine Zeile zählt nur, wenn ein Wert gesetzt ist. Operator-Default "<=".
    Reihenfolge: off → idle → playing.
    """
    out: list[dict[str, Any]] = []
    for state, op_key, val_key in _WATT_ROWS:
        val = src.get(val_key)
        if val in (None, ""):
            continue
        op = src.get(op_key) or "<="
        out.append({"state": state, "op": op, "value": float(val)})
    return out


def _form_from_buckets(buckets: Any) -> dict[str, Any]:
    """Füllt die 6 Watt-Form-Felder aus einer gespeicherten Bucket-Liste."""
    out: dict[str, Any] = {}
    if not isinstance(buckets, list):
        return out
    by_state = {b.get("state"): b for b in buckets if isinstance(b, dict)}
    for state, op_key, val_key in _WATT_ROWS:
        b = by_state.get(state)
        if b:
            out[op_key] = b.get("op")
            out[val_key] = b.get("value")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Entry-Builder (geteilt: Config-Flow + Import)
# ─────────────────────────────────────────────────────────────────────────────


def _build_entry_data(
    device_type: DeviceType, slug: str, field_keys: list[str], src: dict[str, Any]
) -> dict[str, Any]:
    data: dict[str, Any] = {
        CONF_MODULE_ID: MODULE_ID,
        CONF_DEVICE_TYPE: device_type.value,
        CONF_SLUG: slug,
        CONF_DISPLAY_NAME: src.get(CONF_DISPLAY_NAME) or slug,
        CONF_FIELDS: list(field_keys),
    }
    for key in field_keys:
        v = src.get(key)
        if v:
            data[key] = v
    return data


def _build_entry_options(src: dict[str, Any], buckets: list[Any]) -> dict[str, Any]:
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


# ─────────────────────────────────────────────────────────────────────────────
# ConfigFlowHelper
# ─────────────────────────────────────────────────────────────────────────────


class ConfigFlowHelper:
    """Wird vom zentralen BennisToolboxConfigFlow aufgerufen."""

    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow
        self._chosen_type: DeviceType | None = None
        self._meta: dict[str, Any] = {}
        self._field_keys: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="pick_mode", menu_options=["single", "bulk"]
        )

    # ── Einzelnes Gerät ──────────────────────────────────────────────────────

    async def async_step_single(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.flow.async_show_form(
            step_id="module_step", data_schema=_type_step_schema()
        )

    async def async_step_module_step(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not user_input or CONF_DEVICE_TYPE not in user_input:
            return self.flow.async_show_form(
                step_id="module_step", data_schema=_type_step_schema()
            )
        try:
            self._chosen_type = DeviceType(user_input[CONF_DEVICE_TYPE])
        except ValueError:
            return self.flow.async_show_form(
                step_id="module_step",
                data_schema=_type_step_schema(),
                errors={CONF_DEVICE_TYPE: "invalid_type"},
            )
        return self.flow.async_show_form(
            step_id="fields", data_schema=_fields_schema(self._chosen_type, {})
        )

    async def async_step_fields(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._chosen_type is not None
        if user_input is None:
            return self.flow.async_show_form(
                step_id="fields", data_schema=_fields_schema(self._chosen_type, {})
            )

        errors: dict[str, str] = {}
        slug = str(user_input.get(CONF_SLUG, "")).strip().lower()
        if not is_valid_slug(slug):
            errors[CONF_SLUG] = "invalid_slug"
        field_keys = [k for k in (user_input.get(CONF_FIELDS) or []) if k in SLOT_CATALOG]

        if errors:
            return self.flow.async_show_form(
                step_id="fields",
                data_schema=_fields_schema(self._chosen_type, user_input),
                errors=errors,
            )

        self._meta = dict(user_input)
        self._meta[CONF_SLUG] = slug
        self._field_keys = field_keys
        if not field_keys:
            # Kein Feld gewählt → direkt anlegen (Device ohne Slots erlaubt)
            return await self._create_single_entry({})
        return self.flow.async_show_form(
            step_id="slots", data_schema=_slots_schema(field_keys, {})
        )

    async def async_step_slots(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._chosen_type is not None
        if user_input is None:
            return self.flow.async_show_form(
                step_id="slots", data_schema=_slots_schema(self._field_keys, {})
            )
        errors: dict[str, str] = {}
        for key in self._field_keys:
            if not user_input.get(key):
                errors[key] = "required"
        if errors:
            return self.flow.async_show_form(
                step_id="slots",
                data_schema=_slots_schema(self._field_keys, user_input),
                errors=errors,
            )
        return await self._create_single_entry(user_input)

    async def _create_single_entry(self, slot_values: dict[str, Any]) -> FlowResult:
        assert self._chosen_type is not None
        slug = self._meta[CONF_SLUG]
        await self.flow.async_set_unique_id(f"{MODULE_ID}:{slug}")
        self.flow._abort_if_unique_id_configured()
        src = {**self._meta, **slot_values}
        data = _build_entry_data(self._chosen_type, slug, self._field_keys, src)
        buckets = _buckets_from_form(self._meta)
        options = _build_entry_options(self._meta, buckets)
        return self.flow.async_create_entry(
            title=data[CONF_DISPLAY_NAME] or slug, data=data, options=options
        )

    # ── Bulk-Import ──────────────────────────────────────────────────────────

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
        for d in valid:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data={CONF_MODULE_ID: MODULE_ID, **d},
                )
            )
        return self.flow.async_abort(reason="bulk_import_started")

    async def async_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Legt EIN Device aus validierten Import-Daten an (R-DC-08)."""
        err = validate_import_device(import_data)
        if err:
            return self.flow.async_abort(reason="import_invalid")
        device_type = DeviceType(import_data[CONF_DEVICE_TYPE])
        slug = str(import_data[CONF_SLUG]).strip().lower()
        await self.flow.async_set_unique_id(f"{MODULE_ID}:{slug}")
        self.flow._abort_if_unique_id_configured()

        # Felder = alle Slot-Keys die im Import vorkommen
        field_keys = [k for k in ALL_SLOT_KEYS if import_data.get(k)]
        data = _build_entry_data(device_type, slug, field_keys, import_data)
        buckets = import_data.get(CONF_WATT_BUCKETS) or []
        if not isinstance(buckets, list):
            buckets = []
        options = _build_entry_options(import_data, buckets)
        return self.flow.async_create_entry(
            title=data[CONF_DISPLAY_NAME] or slug, data=data, options=options
        )


# ─────────────────────────────────────────────────────────────────────────────
# OptionsFlowHelper
# ─────────────────────────────────────────────────────────────────────────────


class OptionsFlowHelper:
    """Nachträgliches Anpassen: Felder/Slots + Runtime/Watt-Zeilen."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow
        self._field_keys: list[str] = []

    @property
    def device_type(self) -> DeviceType:
        return DeviceType(self.entry.data[CONF_DEVICE_TYPE])

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="init", menu_options=["fields", "runtime"]
        )

    async def async_step_fields(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            defaults = {
                CONF_SLUG: self.entry.data.get(CONF_SLUG, ""),
                CONF_DISPLAY_NAME: self.entry.data.get(CONF_DISPLAY_NAME, ""),
                CONF_FIELDS: self.entry.data.get(CONF_FIELDS)
                or list(default_fields(self.device_type)),
            }
            return self.flow.async_show_form(
                step_id="fields",
                data_schema=_options_fields_schema(self.device_type, defaults),
            )
        self._field_keys = [
            k for k in (user_input.get(CONF_FIELDS) or []) if k in SLOT_CATALOG
        ]
        self._pending_display = user_input.get(CONF_DISPLAY_NAME) or self.entry.data.get(
            CONF_DISPLAY_NAME
        )
        defaults = {k: self.entry.data.get(k) for k in self._field_keys}
        return self.flow.async_show_form(
            step_id="field_values",
            data_schema=_slots_schema(self._field_keys, defaults),
        )

    async def async_step_field_values(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        user_input = user_input or {}
        errors: dict[str, str] = {}
        for key in self._field_keys:
            if not user_input.get(key):
                errors[key] = "required"
        if errors:
            return self.flow.async_show_form(
                step_id="field_values",
                data_schema=_slots_schema(self._field_keys, user_input),
                errors=errors,
            )
        new_data = dict(self.entry.data)
        # Alte Slot-Werte entfernen, neue setzen
        for key in ALL_SLOT_KEYS:
            new_data.pop(key, None)
        for key in self._field_keys:
            if user_input.get(key):
                new_data[key] = user_input[key]
        new_data[CONF_FIELDS] = list(self._field_keys)
        if getattr(self, "_pending_display", None):
            new_data[CONF_DISPLAY_NAME] = self._pending_display
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        return self.flow.async_create_entry(title="", data=self.entry.options)

    async def async_step_runtime(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            buckets = _buckets_from_form(user_input)
            new_options = {
                **self.entry.options,
                CONF_WATT_THRESHOLD_ON: int(
                    user_input.get(CONF_WATT_THRESHOLD_ON, DEFAULT_WATT_THRESHOLD_ON)
                ),
                CONF_STICKY_HOLD_SECONDS: int(
                    user_input.get(
                        CONF_STICKY_HOLD_SECONDS, DEFAULT_STICKY_HOLD_SECONDS
                    )
                ),
                CONF_EXPOSE_SECONDARY_SENSORS: bool(
                    user_input.get(
                        CONF_EXPOSE_SECONDARY_SENSORS, DEFAULT_EXPOSE_SECONDARY_SENSORS
                    )
                ),
                CONF_WATT_BUCKETS: buckets,
            }
            return self.flow.async_create_entry(title="", data=new_options)
        return self.flow.async_show_form(
            step_id="runtime", data_schema=_runtime_schema(self.entry.options)
        )


def _options_fields_schema(
    device_type: DeviceType, defaults: dict[str, Any]
) -> vol.Schema:
    """Options-Variante der Feld-Maske: nur Display + Feld-Multiselect."""
    pre = defaults.get(CONF_FIELDS) or list(default_fields(device_type))
    return vol.Schema(
        {
            vol.Required(
                CONF_DISPLAY_NAME, default=defaults.get(CONF_DISPLAY_NAME, "")
            ): str,
            vol.Required(CONF_FIELDS, default=pre): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(ALL_SLOT_KEYS),
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }
    )


def _runtime_schema(opts: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {
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
    }
    prefill = _form_from_buckets(opts.get(CONF_WATT_BUCKETS))
    for _state, op_key, val_key in _WATT_ROWS:
        op_d = prefill.get(op_key)
        if op_d:
            fields[vol.Optional(op_key, default=op_d)] = _operator_selector()
        else:
            fields[vol.Optional(op_key)] = _operator_selector()
        fields[vol.Optional(val_key, default=prefill.get(val_key))] = vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(min=0, max=10000))
        )
    return vol.Schema(fields)
