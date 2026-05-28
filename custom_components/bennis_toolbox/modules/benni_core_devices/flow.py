"""Config- und Options-Flow für Benni Core · Devices (Single-Hub-Modell).

Config-Flow: legt EINEN Hub-Eintrag "Benni Core · Devices" an (Single-Instance,
keine Felder). Die Geräte werden danach im Options-Flow verwaltet.

Options-Flow (Menü):
- `add_device`    — Typ → Felder-Maske (Anzeigename + Multi-Select) → Slots
                    (Pflicht-Picker) → Runtime (Schwelle/Sticky/Sekundär +
                    Watt-Zeilen nur wenn watt_sensor gewählt)
- `edit_device`   — Gerät wählen → gleiche Schritte vorausgefüllt
- `remove_device` — Gerät wählen → entfernen
- `bulk`          — YAML-Liste → in den Hub mergen

Geräte liegen in `entry.options["devices"]` als Dict {slug: device_conf}.
Der slug wird aus dem Anzeigenamen abgeleitet (nicht mehr manuell getippt).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
import yaml
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers import selector

from ...const import CONF_MODULE_ID
from .const import (
    CONF_BULK_YAML,
    CONF_DEVICE_TYPE,
    CONF_DEVICES,
    CONF_DISPLAY_NAME,
    CONF_EXPOSE_SECONDARY_SENSORS,
    CONF_FIELDS,
    CONF_STICKY_HOLD_SECONDS,
    CONF_WATT_BUCKETS,
    CONF_WATT_IDLE_OP,
    CONF_WATT_IDLE_VALUE,
    CONF_WATT_OFF_OP,
    CONF_WATT_OFF_VALUE,
    CONF_WATT_PLAYING_OP,
    CONF_WATT_PLAYING_VALUE,
    CONF_WATT_SENSOR,
    CONF_WATT_THRESHOLD_ON,
    DEFAULT_EXPOSE_SECONDARY_SENSORS,
    DEFAULT_STICKY_HOLD_SECONDS,
    DEFAULT_WATT_THRESHOLD_ON,
    DEVICE_TYPE_SLUGS,
    MODULE_ID,
    NAME,
    WATT_OPERATOR_CHOICES,
    DeviceType,
)
from .device_types import (
    ALL_SLOT_KEYS,
    SLOT_CATALOG,
    default_fields,
    slugify,
    unique_slug,
    validate_import_payload,
)

# Feld-Labels mit der akzeptierten Domain in Klammern — eindeutig, ohne
# verwirrende Beispiel-Dopplungen. Jedes Feld akzeptiert genau eine Domain
# (siehe SLOT_CATALOG).
FIELD_LABELS: dict[str, str] = {
    "integration_entity": "Media Player (media_player)",
    "power_entity": "An/Aus-Sensor (binary_sensor)",
    "status_entity": "Status-Sensor (sensor)",
    "title_entity": "Titel-Sensor (sensor)",
    "watt_sensor": "Watt-Sensor (sensor)",
    "wifi_sensor": "WLAN-Status (binary_sensor)",
    "switch_entity": "Schalter / Steckdose (switch)",
    "light_entity": "Licht (light)",
    "cover_entity": "Rollo / Cover (cover)",
    "position_entity": "Positions-Sensor (sensor)",
    "climate_entity": "Thermostat / Klima (climate)",
    "value_entity": "Wert-Sensor (sensor)",
}

_WATT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("off", CONF_WATT_OFF_OP, CONF_WATT_OFF_VALUE),
    ("idle", CONF_WATT_IDLE_OP, CONF_WATT_IDLE_VALUE),
    ("playing", CONF_WATT_PLAYING_OP, CONF_WATT_PLAYING_VALUE),
)

# Schlüssel der einklappbaren Watt-Sektion im Runtime-Formular.
WATT_SECTION = "watt_classification"


# ─────────────────────────────────────────────────────────────────────────────
# Schema-Bausteine
# ─────────────────────────────────────────────────────────────────────────────


def _type_schema() -> vol.Schema:
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


def _fields_schema(device_type: DeviceType, defaults: dict[str, Any]) -> vol.Schema:
    """Anzeigename + Multi-Select der zu belegenden Felder. KEIN slug, KEINE
    Watt-/Sekundär-Felder hier (kommen erst nach der Feld-Bestätigung)."""
    pre = defaults.get(CONF_FIELDS) or list(default_fields(device_type))
    options = [
        selector.SelectOptionDict(value=k, label=FIELD_LABELS.get(k, k))
        for k in ALL_SLOT_KEYS
    ]
    return vol.Schema(
        {
            vol.Required(
                CONF_DISPLAY_NAME, default=defaults.get(CONF_DISPLAY_NAME, "")
            ): str,
            vol.Required(CONF_FIELDS, default=pre): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }
    )


def _slots_schema(field_keys: list[str], defaults: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for key in field_keys:
        spec = SLOT_CATALOG.get(key)
        if spec is None:
            continue
        sel = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=list(spec.domains), multiple=False)
        )
        default = defaults.get(key)
        fields[vol.Required(key, default=default) if default else vol.Required(key)] = sel
    return vol.Schema(fields)


def _operator_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(WATT_OPERATOR_CHOICES),
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _runtime_schema(field_keys: list[str], defaults: dict[str, Any]) -> vol.Schema:
    """Schwelle/Sticky/Sekundär — plus optionale, einklappbare Watt-Sektion
    (nur wenn watt_sensor gewählt)."""
    fields: dict[Any, Any] = {
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
    if CONF_WATT_SENSOR in field_keys:
        prefill = _form_from_buckets(defaults.get(CONF_WATT_BUCKETS))
        inner: dict[Any, Any] = {}
        for _state, op_key, val_key in _WATT_ROWS:
            op_d = prefill.get(op_key)
            marker = vol.Optional(op_key, default=op_d) if op_d else vol.Optional(op_key)
            inner[marker] = _operator_selector()
            inner[vol.Optional(val_key, default=prefill.get(val_key))] = vol.Any(
                None, vol.All(vol.Coerce(float), vol.Range(min=0, max=10000))
            )
        # Eingeklappte Sektion → signalisiert klar "optional".
        fields[vol.Optional(WATT_SECTION)] = section(
            vol.Schema(inner), {"collapsed": True}
        )
    return vol.Schema(fields)


def _flatten_runtime(user_input: dict[str, Any]) -> dict[str, Any]:
    """Hebt die Watt-Sektion auf Top-Level, damit _buckets_from_form +
    _build_device_conf wie gewohnt arbeiten."""
    flat = dict(user_input)
    sec = flat.pop(WATT_SECTION, None)
    if isinstance(sec, dict):
        flat.update(sec)
    return flat


def _bulk_schema(default: str = "") -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_BULK_YAML, default=default): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Watt-Bucket-Konvertierung
# ─────────────────────────────────────────────────────────────────────────────


def _buckets_from_form(src: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for state, op_key, val_key in _WATT_ROWS:
        val = src.get(val_key)
        if val in (None, ""):
            continue
        out.append({"state": state, "op": src.get(op_key) or "<=", "value": float(val)})
    return out


def _form_from_buckets(buckets: Any) -> dict[str, Any]:
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


def _build_device_conf(
    device_type: DeviceType,
    display_name: str,
    field_keys: list[str],
    slot_values: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    conf: dict[str, Any] = {
        CONF_DEVICE_TYPE: device_type.value,
        CONF_DISPLAY_NAME: display_name,
        CONF_FIELDS: list(field_keys),
    }
    for key in field_keys:
        if slot_values.get(key):
            conf[key] = slot_values[key]
    conf[CONF_WATT_THRESHOLD_ON] = int(
        runtime.get(CONF_WATT_THRESHOLD_ON, DEFAULT_WATT_THRESHOLD_ON)
    )
    conf[CONF_STICKY_HOLD_SECONDS] = int(
        runtime.get(CONF_STICKY_HOLD_SECONDS, DEFAULT_STICKY_HOLD_SECONDS)
    )
    conf[CONF_EXPOSE_SECONDARY_SENSORS] = bool(
        runtime.get(CONF_EXPOSE_SECONDARY_SENSORS, DEFAULT_EXPOSE_SECONDARY_SENSORS)
    )
    conf[CONF_WATT_BUCKETS] = _buckets_from_form(runtime)
    return conf


# ─────────────────────────────────────────────────────────────────────────────
# ConfigFlowHelper — legt den Hub an (Single-Instance, ohne Felder)
# ─────────────────────────────────────────────────────────────────────────────


class ConfigFlowHelper:
    def __init__(self, hass: HomeAssistant, flow) -> None:
        self.hass = hass
        self.flow = flow

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.flow.async_set_unique_id(f"{MODULE_ID}_hub")
        self.flow._abort_if_unique_id_configured()
        return self.flow.async_create_entry(
            title=NAME,
            data={CONF_MODULE_ID: MODULE_ID},
            options={CONF_DEVICES: {}},
        )


# ─────────────────────────────────────────────────────────────────────────────
# OptionsFlowHelper — Geräteverwaltung
# ─────────────────────────────────────────────────────────────────────────────


class OptionsFlowHelper:
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, flow: OptionsFlow
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.flow = flow
        # Draft-State über die Schritte hinweg
        self._type: DeviceType | None = None
        self._display: str = ""
        self._fields: list[str] = []
        self._slots: dict[str, Any] = {}
        self._editing_slug: str | None = None
        self._runtime_defaults: dict[str, Any] = {}

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _devices(self) -> dict[str, dict[str, Any]]:
        raw = self.entry.options.get(CONF_DEVICES)
        return dict(raw) if isinstance(raw, dict) else {}

    def _save_devices(self, devices: dict[str, dict[str, Any]]) -> FlowResult:
        new_options = {**self.entry.options, CONF_DEVICES: devices}
        return self.flow.async_create_entry(title="", data=new_options)

    # ── Menü ─────────────────────────────────────────────────────────────────

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.flow.async_show_menu(
            step_id="init",
            menu_options=["add_device", "edit_device", "remove_device", "bulk"],
        )

    # ── Gerät hinzufügen ──────────────────────────────────────────────────────

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        self._type = None
        self._editing_slug = None
        self._slots = {}
        self._runtime_defaults = {}
        return self.flow.async_show_form(step_id="add_type", data_schema=_type_schema())

    async def async_step_add_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not user_input or CONF_DEVICE_TYPE not in user_input:
            return self.flow.async_show_form(
                step_id="add_type", data_schema=_type_schema()
            )
        try:
            self._type = DeviceType(user_input[CONF_DEVICE_TYPE])
        except ValueError:
            return self.flow.async_show_form(
                step_id="add_type",
                data_schema=_type_schema(),
                errors={CONF_DEVICE_TYPE: "invalid_type"},
            )
        return self.flow.async_show_form(
            step_id="add_fields", data_schema=_fields_schema(self._type, {})
        )

    async def async_step_add_fields(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._type is not None
        if user_input is None:
            return self.flow.async_show_form(
                step_id="add_fields", data_schema=_fields_schema(self._type, {})
            )
        self._display = str(user_input.get(CONF_DISPLAY_NAME, "")).strip()
        self._fields = [
            k for k in (user_input.get(CONF_FIELDS) or []) if k in SLOT_CATALOG
        ]
        errors: dict[str, str] = {}
        if not self._display:
            errors[CONF_DISPLAY_NAME] = "required"
        if errors:
            return self.flow.async_show_form(
                step_id="add_fields",
                data_schema=_fields_schema(self._type, user_input),
                errors=errors,
            )
        if not self._fields:
            # keine Felder → direkt zur Runtime (Gerät ohne Slots erlaubt)
            return self.flow.async_show_form(
                step_id="add_runtime",
                data_schema=_runtime_schema([], self._runtime_defaults),
            )
        return self.flow.async_show_form(
            step_id="add_slots", data_schema=_slots_schema(self._fields, self._slots)
        )

    async def async_step_add_slots(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.flow.async_show_form(
                step_id="add_slots",
                data_schema=_slots_schema(self._fields, self._slots),
            )
        errors = {k: "required" for k in self._fields if not user_input.get(k)}
        if errors:
            return self.flow.async_show_form(
                step_id="add_slots",
                data_schema=_slots_schema(self._fields, user_input),
                errors=errors,
            )
        self._slots = dict(user_input)
        return self.flow.async_show_form(
            step_id="add_runtime",
            data_schema=_runtime_schema(self._fields, self._runtime_defaults),
        )

    async def async_step_add_runtime(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._type is not None
        if user_input is None:
            return self.flow.async_show_form(
                step_id="add_runtime",
                data_schema=_runtime_schema(self._fields, self._runtime_defaults),
            )
        runtime = _flatten_runtime(user_input)
        conf = _build_device_conf(
            self._type, self._display, self._fields, self._slots, runtime
        )
        devices = self._devices()
        if self._editing_slug and self._editing_slug in devices:
            slug = self._editing_slug
        else:
            slug = unique_slug(slugify(self._display) or "device", set(devices.keys()))
        devices[slug] = conf
        return self._save_devices(devices)

    # ── Gerät bearbeiten ──────────────────────────────────────────────────────

    async def async_step_edit_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        devices = self._devices()
        if not devices:
            return self.flow.async_abort(reason="no_devices")
        if user_input is None:
            return self.flow.async_show_form(
                step_id="edit_device", data_schema=_pick_schema(devices)
            )
        slug = user_input["slug"]
        conf = devices.get(slug)
        if not conf:
            return self.flow.async_abort(reason="no_devices")
        self._editing_slug = slug
        self._type = DeviceType(conf[CONF_DEVICE_TYPE])
        self._display = conf.get(CONF_DISPLAY_NAME, slug)
        self._fields = list(conf.get(CONF_FIELDS) or [])
        self._slots = {k: conf.get(k) for k in self._fields}
        # Runtime-Werte (Schwelle/Sticky/Sekundär/Buckets) für add_runtime
        # vorbefüllen, damit Bearbeiten sie nicht auf Default zurücksetzt.
        self._runtime_defaults = {
            k: v
            for k, v in {
                CONF_WATT_THRESHOLD_ON: conf.get(CONF_WATT_THRESHOLD_ON),
                CONF_STICKY_HOLD_SECONDS: conf.get(CONF_STICKY_HOLD_SECONDS),
                CONF_EXPOSE_SECONDARY_SENSORS: conf.get(CONF_EXPOSE_SECONDARY_SENSORS),
                CONF_WATT_BUCKETS: conf.get(CONF_WATT_BUCKETS),
            }.items()
            if v is not None
        }
        return self.flow.async_show_form(
            step_id="add_fields",
            data_schema=_fields_schema(
                self._type,
                {CONF_DISPLAY_NAME: self._display, CONF_FIELDS: self._fields},
            ),
        )

    # ── Gerät entfernen ───────────────────────────────────────────────────────

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        devices = self._devices()
        if not devices:
            return self.flow.async_abort(reason="no_devices")
        if user_input is None:
            return self.flow.async_show_form(
                step_id="remove_device", data_schema=_pick_schema(devices)
            )
        devices.pop(user_input["slug"], None)
        return self._save_devices(devices)

    # ── Bulk-Import ───────────────────────────────────────────────────────────

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
        # slug ist optional im Bulk-YAML — aus display_name ableiten falls fehlt.
        if isinstance(parsed, list):
            for d in parsed:
                if isinstance(d, dict) and not d.get(CONF_SLUG_KEY):
                    derived = slugify(str(d.get(CONF_DISPLAY_NAME, "")))
                    if derived:
                        d[CONF_SLUG_KEY] = derived
        valid, errors = validate_import_payload(parsed)
        if errors:
            return self.flow.async_show_form(
                step_id="bulk",
                data_schema=_bulk_schema(raw),
                errors={CONF_BULK_YAML: "bulk_invalid"},
                description_placeholders={"errors": "\n".join(errors)},
            )
        devices = self._devices()
        for d in valid:
            slug = d.pop(CONF_SLUG_KEY, None) or unique_slug(
                slugify(d.get(CONF_DISPLAY_NAME, "device")) or "device",
                set(devices.keys()),
            )
            field_keys = [k for k in ALL_SLOT_KEYS if d.get(k)]
            conf: dict[str, Any] = {
                CONF_DEVICE_TYPE: d[CONF_DEVICE_TYPE],
                CONF_DISPLAY_NAME: d.get(CONF_DISPLAY_NAME, slug),
                CONF_FIELDS: field_keys,
            }
            for k in field_keys:
                conf[k] = d[k]
            for k in (
                CONF_WATT_THRESHOLD_ON,
                CONF_STICKY_HOLD_SECONDS,
                CONF_EXPOSE_SECONDARY_SENSORS,
                CONF_WATT_BUCKETS,
            ):
                if k in d:
                    conf[k] = d[k]
            devices[slug] = conf
        return self._save_devices(devices)


# Bulk-YAML darf optional einen expliziten slug mitgeben.
CONF_SLUG_KEY = "slug"


def _pick_schema(devices: dict[str, dict[str, Any]]) -> vol.Schema:
    options = [
        selector.SelectOptionDict(
            value=slug, label=f"{conf.get(CONF_DISPLAY_NAME, slug)} ({slug})"
        )
        for slug, conf in devices.items()
    ]
    return vol.Schema(
        {
            vol.Required("slug"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options, mode=selector.SelectSelectorMode.LIST
                )
            )
        }
    )
