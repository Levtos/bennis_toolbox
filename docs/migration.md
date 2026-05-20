# Migrationsplan

## Stand

Frische HAOS-V3-Installation. Vor Produktivstart wurden die Domains bewusst
final umbenannt. Es gibt **keinen** automatischen Migrationspfad für alte
Config Entries, **keine** Shims, **keine** `async_migrate_entry`-Logik.

## Source of Truth

Dieses Monorepo (`bennis_toolbox`) ist ab sofort die alleinige
**Source of Truth** für alle enthaltenen Custom Integrations. Die alten
Einzel-Repos (`benni_context`, `benni_media_context`,
`benni_notification_router`, `benni_plug_policy`, `ha_wake_planner`,
`Entity-Title-Mapper`, `stash-ha`, `Media_Art_Wrapper`) sind **deprecated**
und können archiviert werden. Eingehende Änderungen erfolgen ausschließlich
hier.

Übernommen wurden u. a. die `benni_media_context`-Tests aus dem alten
Einzelrepo nach [`tests/benni_media_context/`](../tests/benni_media_context/)
und auf das `classifier_*`-Naming aktualisiert
(`etm_ps5` → `classifier_ps5`, …). Die alten Tests im Einzelrepo sind damit
obsolet.

## Finale Domain-Liste

| Ordner / Domain        | Anzeigename            | Frühere Domain (vor Umbenennung) |
| ---------------------- | ---------------------- | --------------------------------- |
| `bennis_toolbox`       | Benni's Toolbox        | (neu)                             |
| `wake_planner`         | Wake Planner           | (unverändert)                     |
| `benni_context`        | Benni Context          | (unverändert)                     |
| `benni_media_context`  | Benni Media Context    | (unverändert)                     |
| `title_classifier`     | Title Classifier       | `etm`                             |
| `notification_router`  | Notification Router    | `benni_notification_router`       |
| `plug_policy_engine`   | Plug Policy Engine     | `benni_plug_policy`               |
| `stash_ha`             | Stash HA               | `stash_player`                    |
| `maw`                  | Media Art Wrapper      | `media_art_wrapper`               |

## Anweisung für die alte Test-HA (falls noch aktiv)

1. In HA → "Integrationen" → die alten Integrationen (`etm`,
   `benni_notification_router`, `benni_plug_policy`, `stash_player`,
   `media_art_wrapper`) **entfernen**. Damit verschwinden die zugehörigen
   Config Entries, Entities und Storage-Dateien.
2. Altes HACS-Repo deinstallieren.
3. `bennis_toolbox` als HACS-Custom-Repository hinzufügen.
4. HA neustarten.
5. Integrationen mit den **finalen Domain-Namen** neu hinzufügen.

> Es gibt absichtlich keinen automatischen Übernahmeweg. Die alten
> Config-Entry-Daten passen nicht zu den neuen Storage-Keys und sollen
> nicht reaktiviert werden.

## Anweisung für die neue HAOS-V3 (Ziel)

1. `bennis_toolbox` per HACS installieren.
2. HA neustarten.
3. Im Integrationsdialog die gewünschten Module hinzufügen — sie erscheinen
   unter den **finalen** Namen (Title Classifier, Notification Router, …).
4. Optional „Benni's Toolbox" hinzufügen für die Übersicht/Health-Sensoren.

## Was die Toolbox bei Legacy-Resten tut

`bennis_toolbox` erkennt zufällig vorhandene alte Config Entries (z. B. wenn
jemand vergisst, `stash_player` zu entfernen) und gibt am Member-Sensor der
neuen Domain einen Hinweis aus:

```
legacy domain detected: stash_player (1 config entry/entries) — remove via UI
```

Die Toolbox migriert nichts und löscht nichts. Sie zeigt nur an.

## Storage-Keys

Wo Integrationen eigene `Store`-Dateien nutzen, wurden die Keys auf die
neue Domain umgestellt:

- `title_classifier`: `STORAGE_KEY_PREFIX = "title_classifier_"`
  (vorher `"etm_"`)
- `notification_router`: `STORAGE_KEY = f"{DOMAIN}_state"` →
  `"notification_router_state"`
- `plug_policy_engine`: `STORAGE_KEY = f"{DOMAIN}_state"` →
  `"plug_policy_engine_state"`

Alte Store-Dateien werden nicht gelesen und müssen — falls vorhanden —
über das Entfernen der Alt-Integration in HA verschwinden.

## Interne Legacy-Bereinigung (Vor-Produktiv-Phase)

Da die Zielinstallation eine frische HAOS-V3 ist und keine alten Config
Entries übernommen werden müssen, wurden auch alle **internen** Legacy-
Begriffe aus dem Produktivcode entfernt — nicht nur die Domain-Namen:

**`benni_media_context`** (vorher / jetzt, alles Breaking-Change-frei für
frische Installation):

| vorher                  | jetzt                              |
| ----------------------- | ---------------------------------- |
| `CONF_ETM_PS5 = "etm_ps5"` | `CONF_TITLE_CLASSIFIER_PS5 = "classifier_ps5"` |
| `CONF_ETM_PC`           | `CONF_TITLE_CLASSIFIER_PC = "classifier_pc"` |
| `CONF_ETM_HOMEPODS`     | `CONF_TITLE_CLASSIFIER_HOMEPODS = "classifier_homepods"` |
| `CONF_ETM_MEDIA`        | `CONF_TITLE_CLASSIFIER_MEDIA = "classifier_media"` |
| `ETM_GAME_DEFAULT/GRIND/HEADSET` | `CLASSIFIER_GAME_DEFAULT/GRIND/HEADSET` |
| `ETM_MEDIA_NORMAL/BOOST/MUTE`    | `CLASSIFIER_MEDIA_NORMAL/BOOST/MUTE` |
| Dataclass-Felder `etm_ps5/etm_pc/…` | `classifier_ps5/classifier_pc/…` |
| Reason-String `"etm_media_mute"` | `"classifier_media_mute"` |
| Translation-Keys `etm_ps5/…`     | `classifier_ps5/…` (matchen die neuen CONF-Werte) |

**`title_classifier`** — Python-Klassennamen:

| vorher                | jetzt                              |
| --------------------- | ---------------------------------- |
| `EtmConfigFlow`       | `TitleClassifierConfigFlow`        |
| `EtmOptionsFlow`      | `TitleClassifierOptionsFlow`       |
| `EtmPanel`            | `TitleClassifierPanel`             |
| `EtmBaseSensor`       | `TitleClassifierBaseSensor`        |
| `EtmEnumSensor`       | `TitleClassifierEnumSensor`        |
| `EtmRawSensor`        | `TitleClassifierRawSensor`         |
| `EtmCatalogSensor`    | `TitleClassifierCatalogSensor`     |
| `EtmCurrentTitleEnumNumber` | `TitleClassifierCurrentTitleEnumNumber` |

Auf frischer HAOS-V3 ist keine Migration nötig — neue Config Entries
werden direkt mit den neuen Keys angelegt. Auf der alten Test-HA muss die
Integration entfernt und neu hinzugefügt werden (siehe oben).

## Domain-Naming-Regel (final)

Teilintegrationen tragen **keinen** `toolbox_`-Präfix in der Domain.
Organisatorische Zugehörigkeit steht im Monorepo und in `bennis_toolbox`,
nicht im Domain-Namen. Domains sind kurz, fachlich und stabil:
`stash_ha`, `maw`, `title_classifier`, `wake_planner`, `benni_context`,
`benni_media_context`, `notification_router`, `plug_policy_engine`. Diese
Regel ist im Test `test_no_toolbox_domain_prefixes` festgeschrieben.
