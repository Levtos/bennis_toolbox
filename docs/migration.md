# Migration & Historie

## Stand 0.2.0

Architektur-Pivot: aus dem Monorepo mit acht eigenständigen
HA-Integrationsdomains wurde eine **echte Umbrella-Integration** mit
genau einer HA-Domain (`bennis_toolbox`) und internen Modulen.

Die Zielinstallation ist eine **frische HAOS-V3**. Es gibt keinen
automatischen Migrationspfad für alte Config-Entries der früheren
Einzelintegrationen. Alte Test-Instanzen müssen die alten Integrationen
manuell entfernen und „Benni's Toolbox" neu hinzufügen.

## Historie

- **0.1.x** — 8 separate `custom_components/<domain>/`, jede eine eigene
  HA-Integration. HACS installierte aus Architekturgründen nur eine
  davon (alphabetisch die erste), daher der Pivot.
- **0.2.0** — Eine HA-Domain `bennis_toolbox`, Module unter
  `bennis_toolbox/modules/<id>/`. Phase-1-Module sind als Spec
  registriert (`PENDING`), Fachlogik wird modulweise aus dem
  Referenzcode portiert.

## Source of Truth

Dieses Repo (https://github.com/Levtos/bennis_toolbox) ist die alleinige
Source of Truth. Die alten Einzel-Repos sind deprecated:

- benni_context
- benni_media_context
- benni_notification_router
- benni_plug_policy
- ha_wake_planner
- Entity-Title-Mapper
- stash-ha
- Media_Art_Wrapper

Der unportierte Code dieser Repos liegt im Monorepo unter `_reference/`
zur Konsultation während der Portierung. `_reference/` wird **nicht**
von HACS ausgeliefert (liegt nicht unter `custom_components/`).

## Portierungsstatus pro Modul

| Modul                   | Status   | Was steht schon | Was fehlt                           |
| ----------------------- | -------- | --------------- | ----------------------------------- |
| `benni_context`         | **READY**| voll portiert: pure logic, Coordinator, Sensoren, Binary-Sensor, Services, 2-Step-Flow, Options-Menü | — |
| `benni_media_context`   | **READY**| pure `logic.py` + `const.py` schon im Modul; jetzt voll portiert: Coordinator (Debounce + ATV-Rollback), 7 Sensoren, 4 Binary-Sensoren, 5 Services, Single-Step-Flow, Options | — |
| `notification_router`   | **READY**| voll portiert: pure routing engine, NotificationRouter mit Rate-Limit/Dedupe/Cooldowns, 2 Sensoren + DND Binary-Sensor, 3 Services, Single-Step-Flow, Options | — |
| `plug_policy_engine`    | **READY**| voll portiert: Decision-Engine, Coordinator, Sensoren, Binary-Sensoren, Services, Config-/Options-Flow, Storage | — |
| `title_classifier`      | **READY**| voll portiert: Storage, Runtime, Sensoren, Number, Services, WS, Panel, Multi-Step-Flow | — |
| `wake_planner`          | **READY**| voll portiert: Coordinator, Sensoren, Binary-Sensor, Services, WS, Panel, Flow | — |
| `maw`                   | STUB     | SPEC            | (später)                            |
| `stash_ha`              | **READY**| voll portiert: GraphQL-Client, Library + Playback Coordinator, 13 Sensoren + Cover-Image + Media-Player, 7 Services, Config-Flow mit Validate, Webhook | — |

Vorgehen pro Modul siehe [module_adapter.md](module_adapter.md).
