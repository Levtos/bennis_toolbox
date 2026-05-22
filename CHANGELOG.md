# Changelog

## 0.3.4 - 2026-05-22

### Behoben

- Cover Policy: Der Options-Flow (Gear-Icon → „Konfigurieren") konnte
  auf HA 2024.12 und neuer nicht geöffnet werden und meldete „500
  Internal Server Error". Ursache war eine Zuweisung an
  `OptionsFlow.config_entry`, das in modernen HA-Versionen eine vom
  Framework gemanagte Property ist. Die Umbrella-Options-Flow nutzt
  jetzt die HA-Konvention und lässt sich wieder öffnen — Menü mit
  `sources`, `profile` und `runtime` erscheint wie vorgesehen.
- Cover Policy: `binary_sensor.*_apply_blocked` blieb auch nach Ablauf
  von `startup_block_seconds` dauerhaft mit `startup_block` markiert,
  wenn nach dem HA-Start keine Source-Entity ihren Zustand änderte.
  Ursache war eine Race-Condition mit `EVENT_HOMEASSISTANT_STARTED`
  plus fehlende garantierte Re-Evaluation am Ablauf des Startup-
  Fensters. Der Coordinator hört jetzt über `async_at_started`
  (deckt „läuft schon" und „startet noch" sauber ab) und plant einen
  einmaligen Timer, der nach `startup_block_seconds + 1` eine
  Re-Evaluation auslöst — dadurch fällt der `startup_block`-Blocker
  zuverlässig weg.

### Tests

- Neuer Regressionstest stellt sicher, dass der Options-Flow
  instanziierbar bleibt, das Menü `sources`/`profile`/`runtime`
  anzeigt und unbekannte Step-Namen an den Modul-Helper
  durchgereicht werden — exakt nach HA-Konvention für die Property.
- Neuer Regressionstest deckt das Startup-Block-Verhalten ab:
  `async_at_started`-Registrierung, einmaliger Expiry-Timer mit
  korrektem Delay, Wegfall des `startup_block`-Blockers nach Ablauf
  und Cancel-Pfad beim Reload.
- Full test suite at release preparation: `367 passed, 2 warnings`.

## 0.3.3 - 2026-05-22

### Behoben

- Geteilte Add-Flow-Übersetzungen sind jetzt modulneutral. Dadurch zeigt
  Plug Policy beim Anlegen nicht mehr die Cover-Policy-Beschreibung oder
  Cover-spezifische Feldtexte.
- `media_context_entity` wird im geteilten Add-Flow neutral beschriftet,
  statt Cover-Policy-spezifisch als Blendschutz-TV-Auslöser.

### Tests

- Regressionstest ergänzt, der modul-spezifische Texte im geteilten
  `module_step` verhindert.
- Full test suite at release preparation: `359 passed, 1 warning`.

## 0.3.2 - 2026-05-22

### Geändert

- Cover Policy schlägt bei neu angelegten Entries lesbare Entity-IDs aus
  der konfigurierten Cover-Entity vor.
  Beispiel: `cover.living_blackout_blind` erzeugt Vorschläge wie
  `sensor.living_blackout_blind_target_position` und
  `binary_sensor.living_blackout_blind_apply_blocked`.
- Die technische `unique_id` der Cover-Policy-Entities bleibt unverändert
  und weiterhin an den Config-Entry gebunden.

### Dokumentiert

- Migration-Hinweis ergänzt: Es gibt bewusst keine automatische
  Entity-Registry-Massenumbenennung. Bestehende manuelle Renames bleiben
  erhalten; neue Entries erhalten die lesbaren Vorschläge automatisch.

### Tests

- Full test suite at release preparation: `356 passed, 1 warning`.

## 0.3.1 - 2026-05-22

### Geändert

- Cover Policy Options-UX verbessert:
  - Zielpositionen werden als 0-100 %-Slider angezeigt.
  - Profilfelder sind nutzerverständlich beschriftet, z. B.
    `Hitzeschutz`, `Blendschutz TV`, `Blendschutz PC`, `Schlafen`,
    `Aufwachen`, `Fenster offen`.
  - Quellen/Auslöser, Zielpositionen und Laufzeitverhalten bleiben im
    Options-Flow klar getrennt.
- Options-Menüs nutzen lesbare Labels statt nackter Step-IDs.

### Behoben

- Cover Policy bleibt fachlich unverändert, aber die Bedienung trennt nun
  deutlicher zwischen Auslösern und Zielpositionen.
- Tests gegen Collection-Order-abhängige Selector-Stubs gehärtet.

### Tests

- Full test suite at release preparation: `342 passed, 1 warning`.

## 0.3.0 - 2026-05-21

### Hinzugefügt

- Produktive Module in die Umbrella-Integration portiert:
  `wake_planner`, `title_classifier`, `benni_context`,
  `benni_media_context`, `plug_policy_engine`, `notification_router`,
  `stash_ha` und `cover_policy`.
- Modul-eigene Entities, Services, Config-Flows, Options-Flows,
  Storage-Helper, WebSocket-Namespaces und Panels ergänzt, wo das Modul
  sie benötigt.
- Wake Planner Profil-UX mit Werktag-, Wochenende-, Feiertag- und
  Einmal-Ausnahmen ergänzt.
- Wake Planner Kalenderkonfliktlogik mit Routinedauer und optionalem
  früherem Wecken ergänzt.
- Wake Planner Calendar Cache mit Throttle, Coalescing und
  Last-known-good-Fallback für CalDAV-Resilienz ergänzt.
- `docs/upcoming_features.md` für akzeptierte Folgearbeiten ergänzt,
  darunter bio-aware Wake/Sleep-Tracking und zukünftige Media-Art-
  Module.
- Release-Prozess dokumentiert.

### Geändert

- Wake Planner Frontend nutzt durchgehend den WebSocket-Namespace
  `bennis_toolbox/wake_planner/*`.
- Wake Planner ruft keine Home-Assistant-Kalender-REST-Endpunkte mehr
  direkt aus dem Panel auf. Kalenderdaten laufen über das Modul-Backend,
  damit rohe CalDAV-Fehler nicht mehr über den UI-Pfad eskalieren.
- Modul-Plattformen werden außerhalb des Event-Loops normalisiert, damit
  HA beim Platform-Setup gültige `Platform`-Werte bekommt.
- CalDAV-basierte Kalenderabfragen prüfen fehlende, nicht verfügbare
  oder durch Startup-Races noch nicht geladene Kalender.
- Wake Planner fragt Feiertage/Termine als Range über den Cache ab,
  statt pro Tag wiederholt Live-CalDAV-Abfragen auszulösen.
- Startup-Refresh wartet auf Home-Assistant-Startup und refreshed
  geladene Entries ohne First-Refresh-APIs im falschen Entry-State zu
  verwenden.
- HACS- und Migrationsdoku bilden den aktuellen READY/STUB-Stand ab.

### Behoben

- Wake Planner erkennt jetzt all-day Feiertags-Events korrekt.
- Wake Planner Thread-Safety-Warnung durch Refresh-Scheduling aus einem
  Nicht-Event-Loop-Callback behoben.
- Wake Planner Today-Ansicht trennt die heutige Entscheidung und den
  nächsten zukünftigen Weckzeitpunkt.
- Modul-Setup-Fehler durch Enum-Stringifizierung als `_P.SENSOR`
  behoben.
- Frontend-WebSocket-Regressionen werden durch Strukturtests verhindert.
- CalDAV-Verbindungsabbrüche blockieren Wake Planner nicht mehr hart:
  bei Fehlern wird ein vorhandener Cache genutzt oder defensiv ein
  degradierter/leerer Event-Satz zurückgegeben.

### Tests

- Full test suite at release preparation: `333 passed, 1 warning`.

### Bekannte Einschränkungen

- `maw` bleibt ein Stub. Media-Art-Fallback und Combined-Media-Player-
  Logik werden als getrennte Toolbox-Module neu gebaut, statt den alten
  verschmolzenen MAW/CMP-Code direkt zu portieren.
- Wake Planner bio-aware Sleep-Tracking ist geplant, aber nicht Teil von
  0.3.0.

## 0.2.0 - 2026-05-20

### Hinzugefügt

- Projekt als echte Home-Assistant-Umbrella-Integration mit einer
  öffentlichen Domain neu aufgebaut: `bennis_toolbox`.
- Modul-Registry, gemeinsamen Modul-Contract, Platform-Dispatcher,
  Service-/WebSocket-Dispatch-Helper, Diagnostics, Übersetzungen und
  HACS-fähiges Paketlayout ergänzt.
- Erste Module-Specs für die Toolbox-Module registriert.
- Erste Struktur- und Logiktests ergänzt.

### Geändert

- Alten Einzelintegrations-Code aus `custom_components/` nach
  `_reference/` verschoben, damit HACS nur
  `custom_components/bennis_toolbox/` installiert.

### Bekannte Einschränkungen

- 0.2.0 war ein Umbrella-Foundation-Release. Die meisten Module waren zu
  diesem Zeitpunkt noch pending oder stubs.
