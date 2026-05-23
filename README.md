# Benni's Toolbox

Eine einzige Home-Assistant-Integration, die mehrere fachlich getrennte
Module unter einem Dach bündelt. HACS installiert **nur** `bennis_toolbox`,
HA zeigt **nur** „Benni's Toolbox" unter „Geräte & Dienste". Module werden
beim Hinzufügen der Toolbox einzeln ausgewählt und konfiguriert.

## Installation in HACS

1. HACS → Custom Repositories → URL `https://github.com/Levtos/bennis_toolbox`,
   Kategorie "Integration".
2. „Benni's Toolbox" installieren.
3. Home Assistant neu starten.

Damit liegt unter `/config/custom_components/` exakt ein Ordner:
`bennis_toolbox/`.

## Modul hinzufügen

In HA → **Einstellungen → Geräte & Dienste → Integration hinzufügen** →
„Benni's Toolbox". Im ersten Schritt wählt der Selector eines der
verfügbaren Module:

| Modul-ID                | Anzeigename            | Status in 0.3.5.7 |
| ----------------------- | ---------------------- | --------------- |
| `benni_context`         | Benni Context          | **ready**       |
| `benni_media_context`   | Benni Media Context    | **ready**       |
| `cover_policy`          | Cover Policy           | **ready**       |
| `notification_router`   | Notification Router    | **ready**       |
| `plug_policy_engine`    | Plug Policy Engine     | **ready**       |
| `title_classifier`      | Title Classifier       | **ready**       |
| `wake_planner`          | Wake Planner           | **ready**       |
| `maw`                   | Media Art Wrapper      | stub            |
| `stash_ha`              | Stash HA               | **ready**       |

**Statuswerte:**
- `ready` — voll lauffähig, Entities/Services aktiv.
- `pending` — Spec ist registriert, Fachlogik liegt unter `_reference/`
  bereit zur Portierung. Config-Entry kann angelegt werden, registriert
  aber noch keine Entities oder Services. Wird in Folge-Releases auf
  `ready` gehoben.
- `stub` — Platzhalter ohne Logik.

Mehrere Instanzen desselben Moduls (z. B. zwei Stash-Server) werden als
separate Config-Entries verwaltet.

## Releases

Der aktuelle Release-Kandidat ist `0.3.5.7`. Änderungen werden in
[CHANGELOG.md](CHANGELOG.md) gepflegt; der Ablauf steht in
[docs/release_process.md](docs/release_process.md).

## Architektur

Genau eine HA-Domain: `bennis_toolbox`. Innerhalb der Integration:

```
custom_components/bennis_toolbox/
  __init__.py            # Dispatch setup/unload an das jeweilige Modul
  manifest.json
  const.py
  config_flow.py         # Modul-Selector + Delegation an ConfigFlowHelper
  diagnostics.py
  services.py            # registriert <module>_<action> unter Domain
  websocket_api.py       # registriert bennis_toolbox/<module>/<cmd>
  storage.py             # Wrapper für Store(...) mit Modul-Präfix
  sensor.py, binary_sensor.py, …   # Platform-Dispatcher (delegieren ans Modul)
  modules/
    __init__.py          # Registry
    base.py              # ModuleSpec / ModuleStatus
    <module_id>/
      __init__.py        # SPEC + async_setup_entry + async_get_entities
      …                  # module-internal files
```

Entities, Services, WebSockets und Storage werden mit der Modul-ID
präfixiert, damit zwischen Modulen nichts kollidiert:

- unique_id: `bennis_toolbox_<module>_<…>`
- Service: `bennis_toolbox.<module>_<action>`
- WebSocket: `bennis_toolbox/<module>/<command>`
- Storage: `.storage/bennis_toolbox_<module>_<suffix>`
- Panel-URL: `bennis_toolbox_<module>` (Sidebar)

## Module portieren

Siehe [docs/module_adapter.md](docs/module_adapter.md) — schrittweise
Anleitung, ein PENDING-Modul auf READY zu heben, basierend auf dem
Referenzcode unter `_reference/`.

## Entwicklung

```bash
pip install -e .[dev]
python -m pytest -q
```
