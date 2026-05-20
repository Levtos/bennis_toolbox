# Benni's Toolbox

Monorepo of Home Assistant custom integrations.

## Architektur

`bennis_toolbox` ist ein **Monorepo**, keine Mega-Integration. Jede fachliche
Integration bleibt eigenständig unter `custom_components/<domain>/` und
behält ihren bisherigen Domain-Namen, Storage-Key und Config-Entries.

Die Dachintegration `bennis_toolbox` ist nur:

- **Navigations-/Übersichtsschicht** (welche Teilintegrationen sind installiert/geladen)
- **Health- und Diagnose-Schicht** (Status-Sensoren, Diagnostics-Dump)
- **kein** Ort für fachliche Logik oder Automationen

Siehe [docs/architecture.md](docs/architecture.md) und [docs/migration.md](docs/migration.md).

## Enthaltene Integrationen

| Ordner / Domain        | Anzeigename            |
| ---------------------- | ---------------------- |
| `bennis_toolbox`       | Benni's Toolbox        |
| `wake_planner`         | Wake Planner           |
| `title_classifier`     | Title Classifier       |
| `benni_context`        | Benni Context          |
| `benni_media_context`  | Benni Media Context    |
| `notification_router`  | Notification Router    |
| `plug_policy_engine`   | Plug Policy Engine     |
| `stash_ha`             | Stash HA               |
| `maw`                  | Media Art Wrapper      |

> Domains sind die **finalen** Namen. Historische Vorgänger und Hinweise für
> die Migration siehe `docs/migration.md`.

## Installation (HACS)

Custom Repository hinzufügen → "Integration" → URL des Repos.
Nach Installation erscheinen alle Teilintegrationen einzeln im
"Integration hinzufügen"-Dialog von Home Assistant.

## Entwicklung

```bash
pip install -e .[dev]
pytest tests/
```
