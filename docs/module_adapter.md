# Modul-Adapter — vom Referenzcode zum READY-Modul

Anleitung, ein `PENDING`-Modul auf `READY` zu heben. Beispiel ist
`benni_context`; das Muster gilt analog für die anderen.

## Ausgangspunkt

- Spec liegt unter `custom_components/bennis_toolbox/modules/<id>/__init__.py`
  mit `status=ModuleStatus.PENDING`.
- Referenzcode der Vor-Architektur unter `_reference/<id>/`.

## Schritte

### 1) Fachdateien ins Modul ziehen

Aus `_reference/<id>/` übernehmen (ggf. umbenennen):

| Referenzdatei        | Zielort im Modul                 |
| -------------------- | -------------------------------- |
| `const.py`           | `modules/<id>/const.py`          |
| `coordinator.py`     | `modules/<id>/coordinator.py`    |
| `logic.py`           | `modules/<id>/logic.py`          |
| `models.py`          | `modules/<id>/models.py`         |
| `sensor.py`          | `modules/<id>/entities/sensor.py` (oder direkt `entities.py`) |
| `binary_sensor.py`   | `modules/<id>/entities/binary_sensor.py` |
| `services.py`        | `modules/<id>/services.py`       |
| `services.yaml`      | wird zu Einträgen in `bennis_toolbox/services.yaml` (Toolbox-Root) |
| `config_flow.py`     | `modules/<id>/flow.py` (umgebaut, siehe 4) |

### 2) `const.py` säubern

Im Referenzcode war `DOMAIN = "<alte_domain>"`. In der neuen Welt heißt
diese Konstante besser `MODULE_ID = "<id>"`. Sie wird vom Modul nur noch
intern benutzt, nie als HA-Integrationsdomain.

```python
# vor
DOMAIN = "benni_context"
STORAGE_KEY = f"{DOMAIN}_state"

# nach
from ...const import storage_key
MODULE_ID = "benni_context"
STORAGE_KEY = storage_key(MODULE_ID, "state")
```

### 3) Coordinator/Logic einbinden

Die Coordinator- und Logikdateien bleiben fachlich, importieren aber
keine HA-`DOMAIN`-Konstanten mehr. `hass.data`-Layout läuft über die
Toolbox:

```python
from ...const import DOMAIN, DATA_ENTRIES

bucket = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id]
bucket["coordinator"] = coordinator
```

### 4) Config-Flow als Helper

Im Referenzcode war `class XConfigFlow(ConfigFlow, domain=DOMAIN):`. Den
Decorator (`domain=DOMAIN`) entfernen — die einzige `ConfigFlow`-
Registrierung kommt aus `custom_components/bennis_toolbox/config_flow.py`.
Stattdessen einen Helper anlegen, den der Umbrella-Flow instanziert:

```python
# modules/<id>/flow.py
class ConfigFlowHelper:
    def __init__(self, hass, flow):
        self.hass = hass
        self.flow = flow  # die umbrella ConfigFlow-Instanz

    async def async_step_init(self, user_input=None):
        if user_input is None:
            return self.flow.async_show_form(
                step_id="module_step",
                data_schema=...,
            )
        # Validierung, etc.
        return self.flow.async_create_entry(
            title="<title>",
            data={"_module_id": "<id>", **user_input},
        )
```

Mehrstufige Flows nutzen `step_id="module_step"` plus
`async_step_module_step(user_input)` im Helper.

Optional analog `class OptionsFlowHelper:` für Options.

### 5) Entities

Eine `async def async_get_entities(hass, entry, platform)`-Funktion im
Modul-`__init__.py` exportieren:

```python
async def async_get_entities(hass, entry, platform):
    from homeassistant.const import Platform
    runtime = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id]
    coord = runtime["coordinator"]
    if platform == Platform.SENSOR:
        return [MyEnumSensor(coord, entry), MyRawSensor(coord, entry)]
    if platform == Platform.BINARY_SENSOR:
        return [MyQuietSensor(coord, entry)]
    return []
```

Entity-`unique_id` immer per Toolbox-Helper:

```python
from ...const import unique_id
self._attr_unique_id = unique_id("benni_context", entry.entry_id, "quiet_mode")
```

### 6) Services & WebSockets

Wenn das Modul Services hat:

```python
# modules/<id>/__init__.py
from ..services import ServiceDef
import voluptuous as vol

async def _set_thing(hass, call): ...

SERVICES = {
    "set_thing": ServiceDef(
        handler=_set_thing,
        schema=vol.Schema({vol.Required("value"): str}),
    ),
}
```

Wird als `bennis_toolbox.<id>_set_thing` registriert.

Für WebSocket-Befehle:

```python
# modules/<id>/__init__.py
from homeassistant.components import websocket_api

@websocket_api.websocket_command({"type": "bennis_toolbox/<id>/list"})
def ws_list(hass, connection, msg): ...

WEBSOCKETS = [ws_list]
```

### 7) Panel (nur title_classifier, wake_planner)

```python
# modules/<id>/__init__.py
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from ...const import panel_url_path

PANEL_URL = f"/{panel_url_path('<id>')}.js"

async def async_register_panel(hass):
    frontend_path = Path(__file__).parent / "frontend" / "<id>-panel.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, str(frontend_path), False)]
    )
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=SPEC.name,
        sidebar_icon=SPEC.icon,
        frontend_url_path=panel_url_path("<id>"),
        config={"_panel_custom": {"name": "<id>-panel", "js_url": PANEL_URL}},
        require_admin=True,
    )
```

### 8) SPEC auf READY heben

```python
SPEC = ModuleSpec(
    module_id="benni_context",
    name="Benni Context",
    description="…",
    status=ModuleStatus.READY,                    # <-- READY
    platforms=(Platform.SENSOR, Platform.BINARY_SENSOR),
    has_services=True,
    has_websocket=False,
    has_panel=False,
)
```

### 9) Tests

- Bestehende Logiktests bleiben — ggf. Imports anpassen.
- Strukturtest (`tests/test_repo_structure.py`) deckt SPEC + Layout ab.
- `pytest tests/` muss grün bleiben.

## Reihenfolge der Portierung (empfohlen)

1. `benni_context` — einfaches Coordinator+Sensor-Pattern, ohne Storage
2. `benni_media_context` — Logik liegt schon im Modul; nur Wiring fehlt
3. `notification_router` — Coordinator + Services
4. `plug_policy_engine` — Coordinator + Decision-Engine
5. `title_classifier` — wegen Panel/WebSocket komplexer
6. `wake_planner` — größtes Modul, am Ende
