# Migration & Historie

## Stand 0.3.0

Architektur-Pivot: aus dem Monorepo mit acht eigenständigen
HA-Integrationsdomains wurde eine **echte Umbrella-Integration** mit
genau einer HA-Domain (`bennis_toolbox`) und internen Modulen.

Die produktiven Pipeline-Module sind in 0.3.0 unter der Umbrella-Domain
READY. Nur `maw` bleibt bewusst STUB, weil Media Art Fallback und
Combined Media Player als getrennte, neu gebaute Toolbox-Module geplant
sind.

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
- **0.3.0** — READY-Port der produktiven Module:
  `wake_planner`, `title_classifier`, `benni_context`,
  `benni_media_context`, `plug_policy_engine`, `notification_router`,
  `stash_ha` und `cover_policy`. Wake Planner wurde zusätzlich mit
  Profil-/Ausnahme-UX, Kalenderkonfliktlogik und CalDAV-Startup-Guards
  gehärtet.

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

## Cover Policy Entity-IDs

`cover_policy` schlägt seit Release 0.3.2 sinnvolle `entity_id`s vor,
abgeleitet aus der konfigurierten `cover_entity`. Bei
`cover.living_blackout_blind` werden initial diese IDs vergeben:

- `sensor.living_blackout_blind_cover_mode`
- `sensor.living_blackout_blind_target_position`
- `sensor.living_blackout_blind_policy_reason`
- `sensor.living_blackout_blind_policy_debug`
- `binary_sensor.living_blackout_blind_apply_blocked`

Bestehende Entity-Registry-Einträge bleiben unangetastet — HA respektiert
`suggested_object_id` nur beim erstmaligen Anlegen einer Entity. Manuelle
Umbenennungen aus älteren Setups bleiben erhalten. `unique_id` ist
unverändert an die `entry_id` gebunden (`bennis_toolbox_cover_policy_<entry_id>_<suffix>`);
ein Wechsel der Cover-Entity ändert die `suggested_object_id`, behält
aber die Identität in der Entity-Registry.

## Portierungsstatus pro Modul

| Modul                   | Status   | Was steht schon | Was fehlt                           |
| ----------------------- | -------- | --------------- | ----------------------------------- |
| `benni_context`         | **READY**| voll portiert: pure logic, Coordinator, Sensoren, Binary-Sensor, Services, 2-Step-Flow, Options-Menü | — |
| `benni_media_context`   | **READY**| pure `logic.py` + `const.py` schon im Modul; jetzt voll portiert: Coordinator (Debounce + ATV-Rollback), 7 Sensoren, 4 Binary-Sensoren, 5 Services, Single-Step-Flow, Options | — |
| `cover_policy`          | **READY**| frischer Neubau: Pure Policy Engine, Coordinator, 4 Sensoren, Binary-Sensor, 4 Services, Config-/Options-Flow, Storage | — |
| `notification_router`   | **READY**| voll portiert: pure routing engine, NotificationRouter mit Rate-Limit/Dedupe/Cooldowns, 2 Sensoren + DND Binary-Sensor, 3 Services, Single-Step-Flow, Options | — |
| `plug_policy_engine`    | **READY**| voll portiert: Decision-Engine, Coordinator, Sensoren, Binary-Sensoren, Services, Config-/Options-Flow, Storage | — |
| `title_classifier`      | **READY**| voll portiert: Storage, Runtime, Sensoren, Number, Services, WS, Panel, Multi-Step-Flow | — |
| `wake_planner`          | **READY**| voll portiert: Coordinator, Sensoren, Binary-Sensor, Services, WS, Panel, Flow, Profil-/Ausnahme-UX, Kalenderkonfliktlogik | Bio-aware Sleep/Wake-Tracking |
| `maw`                   | STUB     | SPEC            | wird nicht 1:1 portiert; `media_art_fallback` + `combined_media_player` sind als getrennte Neubauten geplant |
| `stash_ha`              | **READY**| voll portiert: GraphQL-Client, Library + Playback Coordinator, 13 Sensoren + Cover-Image + Media-Player, 7 Services, Config-Flow mit Validate, Webhook | — |

Vorgehen pro Modul siehe [module_adapter.md](module_adapter.md).
