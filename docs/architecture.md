# Architektur

## Eine Domain, viele Module

`bennis_toolbox` ist eine echte **Umbrella-Integration**: genau eine
HA-Domain, ein HACS-Paket, ein Eintrag in „Geräte & Dienste". Innerhalb
der Integration existieren mehrere fachlich getrennte **Module**, die
intern entkoppelt bleiben, aber gemeinsam unter `bennis_toolbox` laufen.

```
HACS ── installiert ──> custom_components/bennis_toolbox/
                                  │
HA   ── lädt ──>        manifest.json (domain = bennis_toolbox)
                                  │
User ── fügt hinzu ──>  Benni's Toolbox
                                  │
                                  ▼
                  Modul-Selector (Config-Flow Step "user")
                                  │
              ┌───────────┬───────┴────────┬──────────────┐
              ▼           ▼                ▼              ▼
        wake_planner  title_classifier  benni_context  …
        (eigener     (eigener           (eigener      …
         Config-      Config-Entry       Config-
         Entry)        je Instanz)       Entry)
```

Jeder Config-Entry hat Domain `bennis_toolbox`, sein `data["_module_id"]`
benennt das Modul. Das ist HA-Standard — mehrere Entries pro Integration
sind ein bewährtes Pattern.

## Schichten

| Schicht              | Wer                  | Aufgabe                                                                 |
| -------------------- | -------------------- | ----------------------------------------------------------------------- |
| Dispatch             | `bennis_toolbox/__init__.py` | Setup/Unload pro Entry an das richtige Modul weiterleiten          |
| Platform-Dispatch    | `<platform>.py`      | Plattform-Setup pro Entry an das Modul weiterleiten                     |
| Service-Registry     | `services.py`        | Modul-Services unter `bennis_toolbox.<module>_<action>` registrieren    |
| WebSocket-Registry   | `websocket_api.py`   | `bennis_toolbox/<module>/<cmd>` registrieren                            |
| Storage-Helper       | `storage.py`         | `Store(..., bennis_toolbox_<module>_<suffix>)`                          |
| Modul-Registry       | `modules/__init__.py`| Welche Module gibt es, lazy import per ID                                |
| Modul-Contract       | `modules/base.py`    | `ModuleSpec`, `ModuleStatus`                                            |
| Fachlogik            | `modules/<id>/…`     | Eigene Coordinator, Entities, Logik — entkoppelt von anderen Modulen     |

## Entkopplungsregeln

1. **Module importieren sich nicht gegenseitig.** Test
   `test_no_cross_module_imports` sperrt das ab.
2. **Module reden nur über HA-Bus oder über Entity-States miteinander**,
   nicht über Python-Imports. Wenn `notification_router` z. B. einen
   Quiet-Mode-Status braucht, liest er ihn aus einer Entity, die
   `benni_media_context` exponiert — nicht aus dessen Modulen.
3. **Modul-IDs sind die einzige Cross-Modul-Namensquelle** (für Storage-
   und Service-Präfixe). Sie sind im Code als Strings festgepinnt und im
   Test gegen den Ordnernamen verifiziert.
4. **Kein `toolbox_`-Präfix in Modul-IDs.** Organisatorische Zugehörigkeit
   sitzt in der Toolbox, nicht im Namen jedes Moduls.

## Status-Modell

Jedes Modul deklariert in seinem `SPEC` einen Status:

- **READY** — voll lauffähig. Umbrella ruft `async_setup_entry`, lädt
  Platforms, registriert Services/WebSockets/Panels.
- **PENDING** — Spec da, Logik noch nicht portiert. Umbrella legt den
  Entry als no-op an, damit der User das Modul vormerken kann. Kein
  Crash, keine Entities.
- **STUB** — Platzhalter ohne Logik.
- **HIDDEN** — wird im Selector nicht angezeigt.

## Tests

Alle Tests laufen aus dem Repo-Root mit `pytest tests/`. Der Strukturtest
([tests/test_repo_structure.py](../tests/test_repo_structure.py))
garantiert:

- nur `bennis_toolbox/` unter `custom_components/`
- alle 8 erwarteten Module sind vorhanden, jedes hat ein gültiges SPEC
- Modul-`__init__.py` ist ohne `homeassistant`-Abhängigkeit ladbar
  (damit die Registry beim Boot keine Importfallen hat)
- keine Cross-Modul-Imports
- keine Alt-Domain-Tokens im Produktivcode
- alle Platform-Dispatcher delegieren an `async_setup_platform_for`

Modul-spezifische Tests (z. B. `tests/benni_media_context/test_logic.py`)
testen reine Python-Logik der Module ohne HA-Mock.
