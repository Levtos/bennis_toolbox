# Changelog

## 0.3.5.7 - 2026-05-22

### Geändert

- Benni Media Context: `subwoofer_allowed` berücksichtigt jetzt den
  Denon-Audio-Pfad. PC-Gaming über Denon/TV-Audio lässt den Subwoofer
  zu, auch wenn ein Fenster offen ist — vorher schaltete schon das
  offene Fenster den Sub allein aus.
- Subwoofer-Policy mit klarer Blocker-Reihenfolge und Diagnose:
  1. Quiet Mode → off, reason `quiet_mode`
  2. keine Entertainment-Aktivität → off, reason `no_entertainment`
  3. Headset aktiv (z. B. `gaming_headset` Classifier) → off, reason
     `headset_active`
  4. Fenster offen UND kein Denon-Pfad → off, reason
     `window_open_no_denon_path`
  5. sonst → on
- `gaming_grind` blockiert den Subwoofer NICHT — das gab es vorher
  schon nicht und wird via Regression-Test fixiert, damit ein
  zukünftiger Blocker nur bewusst eingeführt werden kann.

### Hinzugefügt

- Snapshot trägt `denon_source` (`source`-Attribut der Denon
  `media_player`-Entity, z. B. „TV Audio"). Wenn die konfigurierte
  Denon-Entity ein `media_player` ist, reicht ein gesetzter
  Source-Wert allein, um den Denon-Audio-Pfad als aktiv zu erkennen
  — die `denon_active`-Binary ist nicht mehr Pflicht.
- Decision trägt `denon_audio_path` und `subwoofer_block_reason` als
  Diagnose-Felder.
- `binary_sensor.benni_media_context_subwoofer_allowed` zeigt die
  Diagnose als Attribute: `denon_active`, `denon_source`,
  `denon_audio_path`, `subwoofer_block_reason`.

### Tests

- Neuer `test_subwoofer_policy.py` mit 11 Tests: PC-Gaming
  Denon-off/on, Source-only-Erkennung, „off"-Source zählt nicht,
  Fenster auf mit/ohne Denon, Quiet/Headset-Blocks, Idle-Block,
  Denon-only Streaming, `gaming_grind` Regression.
- benni_media_context: +11 Tests.
- Full test suite at release preparation: `462 passed, 2 warnings`.

## 0.3.5.6 - 2026-05-22

### Behoben

- Benni Media Context: Über das Gear-Icon ließen sich nach dem
  Anlegen nur noch die Volume-/Debounce-Knöpfe ändern. Die
  Medienquellen (TV, AppleTV, PS5, HomePods, Title-Classifier, …)
  waren im Options-Flow gar nicht erreichbar — ein Wechsel
  erforderte bis dato Entry löschen und neu anlegen. Der
  Options-Flow zeigt jetzt ein Menü mit zwei Schritten:
  - **Auslöser & Quellen** — alle Medien-Source-Entities.
  - **Lautstärke & Debounce** — die bisherigen Tuning-Knöpfe.
- Benni Media Context: Coordinator liest Source-Entities nun via
  Merge `entry.options` → `entry.data`. Bestehende Entries laufen
  unverändert weiter (Werte bleiben in `data`); Edits aus dem neuen
  Source-Step landen in `options` und überschreiben den Default
  sofort, ohne Migration.

### Tests

- Neuer `test_options_sources_menu.py`: Menü zeigt `sources` und
  `tuning`; Sources-Step rendert die Quellen-Schema, übernimmt
  Defaults aus `entry.data`, persistiert in `entry.options`, lässt
  leere Slots weg (damit der Data-Fallback im Coordinator greift)
  und kollidiert nicht mit Tuning-Optionen.
- benni_media_context: +6 Tests.
- Full test suite at release preparation: `451 passed, 2 warnings`.

## 0.3.5.5 - 2026-05-22

### Behoben

- Wake Planner: `sensor.wake_planner_<slug>_wake_state` blieb seit
  0.3.5.4 dauerhaft auf `unknown`, obwohl der Coordinator
  Decisions korrekt produzierte und `next_wake` / `wake_needed` sauber
  liefen. Ursache war eine HA-Validierungs-Stolperfalle: sobald die
  Umbrella-Translations die `entity.sensor.wake_state.state.*`-Keys
  ausspielen, behandelt HA den Sensor als Enum und prüft den Wert
  gegen die `options`-Liste der Entity-Description. Die war nicht
  gesetzt — also wurde jeder Zustand als ungültig verworfen und HA
  fiel auf `unknown` zurück. Fix: `device_class=SensorDeviceClass.
  ENUM` plus `options=[…alle WakeState-Werte…]` deklariert.

### Tests

- Regressionstest pinnt `device_class=enum` und `options` der
  `wake_state`-Description, plus parametrisierter Test, der für jeden
  `WakeState`-Wert (scheduled/skipped/overridden/holiday/inactive)
  prüft, dass der Sensor den korrekten String liefert und nicht in
  `unknown` fällt. Zusätzlicher Test bestätigt, dass `None` nur dann
  durchkommt, wenn der Coordinator wirklich noch keine Decision hat.
- wake_planner: +7 Tests.
- Full test suite at release preparation: `445 passed, 2 warnings`.

## 0.3.5.4 - 2026-05-22

### Geändert

- Wake Planner: Eindeutige Entity-IDs für die Outputs, damit
  `benni_context` ohne Rätselraten auf `wake_next` und `wake_needed`
  zugreifen kann. Neue Entries landen jetzt auf:
  - `binary_sensor.wake_planner_<slug>_wake_needed`
  - `sensor.wake_planner_<slug>_next_wake`
  - `sensor.wake_planner_<slug>_wake_state`
  Der Wake-needed-Binary-Sensor ist exakt das Wake-Fenster: `on` nur
  wenn der State `scheduled` oder `overridden` ist und `now` zwischen
  `wake_window_start` und `wake_window_end` liegt.
- Wake Planner: Die deutschen Namen „Wecken nötig", „Nächster Wecker",
  „Weckstatus" sind jetzt aus der Umbrella-Translations-Datei
  bedient, statt aus HAs Device-Class-Fallback (der zu
  „Betriebszustand" und „Zeitstempel" führte). State-Übersetzungen
  für `scheduled`/`skipped`/`overridden`/`holiday`/`inactive`
  ergänzt.
- `unique_id` aller Wake-Planner-Entities bleibt unverändert —
  bestehende Registry-Einträge keep ihre Identität. Für lesbare
  Entity-IDs in alten Setups manuell umbenennen oder Entry neu
  anlegen (suggested_object_id greift nur beim Erstanlegen, das ist
  HA-Konvention).

### Tests

- Neuer `tests/wake_planner/test_entity_outputs.py`: pin
  suggested_object_id für alle drei Entities, halten unique_id
  unverändert, decken die wake-needed-Wahrheitstabelle für alle
  `WakeState`-Varianten ab (inside/outside window, missing window,
  no decision) und prüfen, dass der next-wake-Sensor einen
  timezone-aware Timestamp liefert.
- wake_planner: +15 Tests.
- Full test suite at release preparation: `438 passed, 2 warnings`.

## 0.3.5.3 - 2026-05-22

### Behoben

- Plug Policy Engine: Policy `HB` (Home Baseline) hat fälschlich
  auto-off ausgelöst, wenn der Haushalt wirklich abwesend war und das
  Gerät idle. HB ist eine Baseline-Policy und darf niemals
  automatisch ausschalten; nur Policy `AC` (Away Cut) ist dafür
  zuständig. `_decide_baseline_or_away` ist nun in zwei klar
  getrennte Zweige aufgeteilt:
  - HB: aktive/unknown-as-aktive Geräte bleiben weiterhin per
    `never_cut_when_active` geschützt; alle übrigen Fälle inklusive
    truly-away + idle liefern `KEEP` mit aussagekräftigem Grund
    („HB: away + idle — no baseline action (HB is not an away-cut
    policy)").
  - AC: schaltet weiterhin truly-away + idle aus, ignoriert
    `bei_eltern` als zuhause-äquivalent.
- Plug Policy Engine: Identischer Bug in `_decide_appliance` ebenfalls
  korrigiert. Großgeräte mit Policy `HB` bleiben jetzt auch im
  truly-away-Idle-Fall auf `KEEP`; nur `AC` darf hier abschalten.
  Running- und Unknown-Power-Fälle bleiben über beide Policies hinweg
  protected.

### Tests

- Neuer `test_hb_baseline_semantics.py` mit 12 Tests: generisches
  Gerät HB vs. AC, Appliance HB vs. AC, never-cut-when-active,
  `bei_eltern`, unknown-power-as-active.
- Bestehende `test_hb_cuts_when_idle_and_truly_away` und
  `test_appliance_idle_and_away_cuts` an die korrigierte Semantik
  angepasst (alte Tests dokumentierten den Bug).
- plug_policy_engine: 96 passed (+12).
- Full test suite at release preparation: `423 passed, 2 warnings`.

## 0.3.5.2 - 2026-05-22

### Behoben

- Plug Policy Engine: Der Sensor-Schritt im Add/Edit-Flow zeigte beim
  Anlegen von Geräten ohne erkannten Leistungssensor (z. B.
  Subwoofer) den Fehler „Entity None is neither a valid entity ID nor
  a valid UUID" und blockierte das Speichern. Ursache: die Optional-
  Marker für `power_entity` und `battery_entity` wurden mit
  `default=None` registriert, was HAs EntitySelector als ungültigen
  Wert ablehnt. Die Defaults werden nun nur noch gesetzt, wenn ein
  echter Wert vorliegt — leere Slots bleiben einfach leer und
  übergehen die Validierung.
- Plug Policy Engine: Der gleiche Fix wurde auf alle globalen
  Entity-Slots (Presence, Bio, Day, Media, Entertainment, Activity)
  angewandt, damit auch der erste Anlege-Schritt nicht stolpert, wenn
  ein Slot bewusst leer bleiben soll.

### Tests

- Regressionstest: Sensoren-Schritt für den Subwoofer (kein
  Power-Sensor) darf keinen `None`-Default am `power_entity`-Slot
  setzen und muss eine leere Submission sauber an den
  Erweitert-Schritt weiterreichen.
- plug_policy_engine: 84 passed (+1).
- Full test suite at release preparation: `411 passed, 2 warnings`.

## 0.3.5.1 - 2026-05-22

### Hinzugefügt

- Plug Policy Engine: Device-Presets für bekannte Einhornzentrale-Plug-
  Rollen. Wird im Add-Flow ein bekannter Schalter wie
  `switch.living_pc_plug`, `switch.living_denon_plug`,
  `switch.kitchen_washing_machine_plug` oder die Kaffeemaschine
  ausgewählt, setzt die Toolbox `kind`, `active_threshold`,
  `idle_threshold`, `deadband_lower`/`deadband_upper`,
  `unknown_behavior`, `never_cut_when_active` und `wake_signal_only`
  automatisch auf die fachlich geprüften Defaults. Subwoofer (ohne
  Power-Sensor) wird konservativ auf `assume_active` festgenagelt.
- Presets erscheinen als Hinweis im Sensoren- und Erweitert-Step
  ("Preset erkannt: living_pc_plug / PC safe defaults"). Bei
  unbekannten Schaltern zeigt der Flow "Kein bekanntes Preset,
  generische Defaults".

### Verhalten

- Presets greifen nur im Add-Flow und nur auf leere Slots im aktuellen
  Draft. Nutzerwerte, die in basics oder sensors gerade gesetzt
  wurden, werden nicht überschrieben.
- Edit-Flow wendet niemals Presets an — bestehende Geräte behalten
  ihre gespeicherten Schwellwerte und Hidden-/Legacy-Keys.
- `enable_control` bleibt unverändert default `false`.

### Tests

- Plug Policy Engine: Preset-Lookup für PC, Switch, Denon, Appliance,
  Coffee, TV, PS5, Subwoofer und die drei Großgeräte-Plugs. Preset +
  Atomic-Power-Suggestion arbeiten zusammen. Edit-Flow überschreibt
  weder bestehende Werte noch Legacy-Keys. Unbekannte Plugs fallen auf
  generische Defaults zurück.
- plug_policy_engine: 83 tests (+13 neu)
- Full test suite at release preparation: `410 passed, 2 warnings`.

## 0.3.5 - 2026-05-22

### Geändert

- Plug Policy Engine: Add/Edit eines Geräts ist in drei klar getrennte
  Schritte aufgeteilt — Grunddaten, Sensoren, erweiterte Schwellwerte.
  Die UI zeigt nur noch Felder, die für die gewählte Geräteart und
  Policy fachlich relevant sind. Tablet-, Diffuser-, Wake-Signal- und
  Schedule-Context-Felder erscheinen nur dort, wo sie tatsächlich
  wirken; `allowed_contexts` taucht nur bei Policy `SC` auf.
- Plug Policy Engine: Wird ein Schalter wie `switch.living_pc_plug`
  gewählt, schlägt die Toolbox passende Sensor-Entities automatisch
  vor. Priorität bevorzugt Einhornzentrale-Atomic-Aggregatoren
  (`sensor.<slug>_power_atomic`, `sensor.<slug>_battery_atomic`) vor
  den Rohsensoren. Voltage/Current/Energy werden rein informativ
  erwähnt; ein vom Nutzer gesetzter Wert wird nie überschrieben.
- Plug Policy Engine: Detaillierte Day-State-Werte wie `late_morning`,
  `afternoon`, `early_evening`, `early_night` werden im Engine zentral
  auf die groben Buckets `morning` / `day` / `evening` / `night`
  abgebildet, gegen die `allowed_contexts` matched. Bestehende
  Coarse-Werte funktionieren unverändert; unbekannte Strings bleiben
  durchgereicht.

### UX

- Plug Policy Engine: Übersetzungen für alle neuen Step-Titel und
  Feldbeschriftungen in `de.json` und `en.json` ergänzt, inklusive
  Hinweis am `allowed_contexts`-Label, dass das Day-State-Mapping
  intern erfolgt.

### Tests

- Plug Policy Engine UX: Tests für Multi-Step Add/Edit, Auto-Detection
  inklusive Atomic-Priorität, Kind-gefilterte Felder und Edit-Flow,
  der bestehende und nicht gerenderte Legacy-Keys preserved.
- Plug Policy Engine Engine: Tests für den Day-Phase-Mapper und das
  SC-Matching unter `late_morning` / `late_evening` / `early_night`,
  plus Backwards-Compat für die plain `morning`/`day`/`evening`/`night`-
  Werte.
- Full test suite at release preparation: `397 passed, 2 warnings`.

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
