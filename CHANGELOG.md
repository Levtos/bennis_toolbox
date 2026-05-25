# Changelog

## 0.3.8.1 - 2026-05-25

### Behoben

- **Benni Media Context: `NameError: name '_BaseBinary' is not defined`
  beim Entry-Setup.** Die in 0.3.8 hinzugefügte Klasse
  `_VolumeApplyAllowed(_BaseBinary)` stand fälschlicherweise im
  Sensor-Block von [entities.py](custom_components/bennis_toolbox/modules/benni_media_context/entities.py)
  — also *vor* der Definition von `_BaseBinary`. Python erkennt
  Forward-References auf Basisklassen erst beim tatsächlichen
  Modul-Import; das passierte im HA-Setup, nicht aber in den
  bisherigen AST-/Stub-Tests. Klasse jetzt korrekt zu den anderen
  Orchestrator-Binarys nach `_HomePodsResumeAllowed` verschoben.

### Tests

- Neuer `test_entities_definition_order.py` (3 Tests) als statische
  AST-Regression: jede Klasse, die `_BaseSensor` / `_BaseBinary`
  erbt, muss diese Basisklasse vorher im Quelltext sehen.
  Verifiziert auch konkret, dass `_VolumeApplyAllowed` → `_BaseBinary`
  und `_VolumePolicySensor` → `_BaseSensor` jeweils nach ihrer
  Basis stehen. Die Heuristik fängt diesen Fehler-Typ generisch
  für alle künftigen Entity-Klassen.
- Full suite: **659 passed** (+3, von 656).

## 0.3.8 - 2026-05-25

### Hinzugefügt

- **Benni Media Context: Konfigurierbare Orchestrator-Inputs.** Sämtliche
  Eingänge des Audio- und Volume-Orchestrators sind jetzt über
  Config-Entry-Options auswählbar — keine harten Entity-IDs, keine
  Blindheuristik. Es gibt eine zentrale Input-Registry (`ORCH_INPUTS`)
  als Single Source of Truth; der Coordinator löst alle Slots mit
  Legacy-Fallback auf und liefert sie über `configured_entities` und
  `missing_orchestrator_inputs` / `missing_volume_inputs` an die
  Debug-Attribute.
- **Neue Options-Cards:**
  - „Orchestrator": Picker für `bio_state_entity`,
    `manual_playback_entity`, `planned_radio_entity`,
    `pc_gaming_active_entity`, `media_stop_latch_entity`,
    `opening_any_open_entity`, `quiet_mode_entity` — mit Domain-
    Filter pro Slot.
  - „Volume": 9 Tuning-Felder (`volume_homepods_media_base`,
    `volume_denon_media_base`, `volume_ducked_target`,
    `volume_homepods_max`, `volume_denon_max`, `volume_active_min`,
    `volume_night_offset`, `volume_edge_day_offset`,
    `volume_opening_offset`) als bare TextSelector mit Dot/Komma-
    Coercion und Range-Check im Step-Handler.
- **Volume-Orchestrator** (`volume_orchestrator.py`) als reine
  Entscheidungslogik, getrennt vom Audio-Orchestrator. Audio entscheidet
  Owner/Aktion; Volume entscheidet Ziel-Lautstärken + Apply-Erlaubnis.
- **Neue HA-Entities:**
  - `sensor.benni_media_context_volume_policy`
    — `idle`, `media`, `ducked`, `muted`, `blocked`.
  - `sensor.benni_media_context_volume_target_homepods`
    — Float 0.0–1.0 oder `unavailable` (HomePods nicht konfiguriert
    bzw. policy=`muted`/`blocked`).
  - `sensor.benni_media_context_volume_target_denon`
    — analog für Denon.
  - `binary_sensor.benni_media_context_volume_apply_allowed`.
- Jede Audio- und Volume-Entity trägt das volle gemeinsame
  Debug-Attribut-Set: `reason`, `blocked_reason`,
  `configured_entities`, `missing_orchestrator_inputs`,
  `missing_volume_inputs`, `media_context`, `media_subcontext`,
  `media_device`, `gaming_source`, `gaming_platform`,
  `entertainment_active`, `audio_owner`, `homepods_state`,
  `denon_state`, `tv_state`, `appletv_state`, `ps5_state`,
  `switch_state`, `pc_gaming_active`, `manual_playback_active`,
  `planned_radio_active`, `media_stop_latch`, `bio_state`,
  `day_state`, `opening_any_open`, `quiet_mode_active`,
  `base_homepods_target`, `base_denon_target`,
  `effective_homepods_target`, `effective_denon_target`,
  `day_offset`, `opening_offset`, plus die bisherige
  Signal-Aufschlüsselung.

### Audio-Orchestrator Änderungen

- Liest `pc_gaming_active_entity` (wenn konfiguriert) zuerst — das
  überschreibt die Title-Classifier-Heuristik. Bloß angeschalteter PC
  pausiert weiterhin keine HomePods.
- `media_stop_latch_entity` (wenn konfiguriert) wird zum externen
  Stop-Latch und übersteuert die interne Manual-Stop-Buchführung.
- `quiet_mode_entity` (wenn konfiguriert) wird zur autoritativen
  Quiet-Mode-Quelle; die Tür/Anruf/Aktivitäts-Heuristik bleibt als
  Fallback.
- Wenn `homepods_player_entity` fehlt → `action=none`,
  `blocked_reason="homepods_entity_missing"` — kein Pause/Resume gegen
  eine Phantom-Entity.

### Volume-Fachregeln

- `blocked` wenn weder HomePods noch Denon konfiguriert.
- `muted` (apply_allowed=False) bei `bio_sleep`.
- `ducked` (apply_allowed=True, aktives Gerät auf
  `volume_ducked_target`) bei Quiet Mode.
- `media`: Owner=`homepods` → HomePods aktiv, Denon=0; Owner=
  `tv_denon`/`gaming_stack`/`private_stack` → Denon aktiv,
  HomePods=0.
- `idle`: beide Ziele 0.
- Day-Offset: `night`/`late_night`/`early_night` →
  `volume_night_offset`; `early_morning`/`late_evening` →
  `volume_edge_day_offset`; sonst 0.
- `opening_any_open` true → `volume_opening_offset` zusätzlich.
- Clamps: aktives Ziel mindestens `volume_active_min`, HomePods max
  `volume_homepods_max`, Denon max `volume_denon_max`. Stiller Kanal
  bleibt 0, Offsets bumpen ihn nicht hoch.

### Tests

- `test_volume_orchestrator.py`: 25 Tests für die volle Volume-Matrix
  (idle, owner-Routing, quiet-mode-ducked, sleep-mute, blocked-no-
  speakers, Night/Edge/Opening-Offsets stacken, Active-Min-Floor,
  Max-Cap, partielle Speaker-Konfiguration, Debug-Echo).
- `test_options_orchestrator_and_volume.py`: 12 Tests für die zwei
  neuen Options-Cards (Menu-Eintrag, alle Slots im Schema,
  Save/Clear-Semantik, Dot-Default-Rendering,
  Komma-Submit-Roundtrip, `out_of_range`/`invalid_number`/Blank-
  Verhalten).
- `test_orchestrator.py`: 8 neue Regressions für die
  konfigurierten-Inputs-Surface (echoed `configured_entities`,
  `missing_homepods_entity_blocks_action`, externes
  `pc_gaming_active` true/false überschreibt Classifier,
  `media_stop_latch` setzt manual_stop, externes
  `quiet_mode_entity` true/false überschreibt Heuristik,
  `bio_state`/`day_state` Echo).
- Smoke-Test um die zwei neuen Entity-Keys erweitert.
- **Full suite: 656 passed, 2 warnings** (+43, von 613).

### Kompatibilität

- Keine Migration nötig. Bestehende Entries laufen weiter — Volume-
  Defaults greifen, sobald die Options leer sind.
- Bestehende Sensor-Keys (`volume_target_homepods`,
  `volume_target_denon`) bleiben stabil; ihre Werte kommen jetzt
  jedoch aus dem Volume-Orchestrator statt aus der Legacy
  `compute_volumes()`-Berechnung.
- `homepods_player_entity` ist der einzige als "required" markierte
  Orchestrator-Input — ohne ihn wird der Audio-Orchestrator explizit
  blockiert statt zu raten.

## 0.3.7 - 2026-05-25

### Hinzugefügt

- Benni Media Context: HomePods-vs-Entertainment Audio-Orchestrator als
  reine Entscheidungslogik. Erweitert das Modul um stabile HA-Entities,
  ohne selbst Services aufzurufen — YAML reagiert nur noch auf das
  berechnete Ergebnis.
- Neue Outputs:
  - `binary_sensor.benni_media_context_homepods_should_pause`
  - `binary_sensor.benni_media_context_homepods_resume_allowed`
  - `sensor.benni_media_context_homepods_action`
    (Werte `none`, `pause_homepods`, `resume_homepods`, `start_radio`)
  - `sensor.benni_media_context_audio_owner`
    (Werte `none`, `homepods`, `tv_denon`, `gaming_stack`,
    `private_stack`)
- Jede Orchestrator-Entity trägt das gleiche Debug-Attribut-Set:
  `reason`, `blocked_reason`, `media_context`, `media_subcontext`,
  `media_device`, `gaming_source`, `gaming_platform`,
  `entertainment_active`, `tv_state`, `appletv_state`, `ps5_state`,
  `switch_state`, `pc_gaming_active`, `denon_state`,
  `denon_audio_path`, `homepods_state`, `manual_playback_active`,
  `planned_radio_active`, `bio_sleep`, `auto_paused_homepods`,
  `resume_candidate`, `winning_stack`, sowie die Signal-Aufschlüsselung
  (`private_signal_active`, `gaming_signal_active`,
  `streaming_signal_active`, `tv_signal_active`, `ps5_gaming_active`,
  `switch_gaming_active`).
- Neue, optionale Konfigurationsquellen (kein UI-Eintrag — über
  `entry.data`/`options`): `bio_state_entity` (sleep/sleeping blockiert
  Resume), `manual_playback_entity` (manuell laufende Musik),
  `planned_radio_entity` (geplantes Radio).

### Fachregeln

- Priorität: `private_time` > `gaming` > `streaming`/`tv` > `homepods`
  > `idle`.
- PS5 und Switch (gedockt) sind immer Entertainment-Stack.
- PC-Gaming zählt nur bei validem Title-Classifier-Wert
  (`classifier_pc != 0`); ein bloß eingeschalteter PC pausiert HomePods
  nicht.
- Apple-TV-Streaming-Apps gewinnen gegen HomePods; Apple-TV-System-Apps
  (Home/Settings) zählen nicht als Streaming.
- HomePods werden nach Ende des Entertainment-Stacks nur fortgesetzt,
  wenn sie zuvor automatisch pausiert wurden. Manueller Stop blockiert
  Resume bis zum nächsten Start.
- `bio_sleep` (Bio-State `sleep`/`sleeping`/`asleep`) blockiert sowohl
  Resume als auch geplanten Radio-Start.
- War vorher geplantes Radio aktiv, empfiehlt der Orchestrator nach
  Entertainment-Ende `start_radio`; sonst (falls manuelle Musik lief)
  `resume_homepods`.

### Behoben

- Benni Media Context: Das Options-Menü „Lautstärke & Debounce“
  warf in HA einen Render-Fehler, weil die Tuning-Felder über
  `vol.All(TextSelector, _to_decimal, vol.Range)` definiert waren —
  HA's `voluptuous_serialize` extrahiert den Selector nicht
  zuverlässig aus einer `vol.All`-Kette, je nach HA-Version. Schema
  baut jetzt jedes Feld als bare `selector.TextSelector`. Coercion
  (Dot/Komma-Dezimal) und Range-Check laufen im Step-Handler
  `async_step_tuning`. Ungültige Eingaben zeigen das Formular erneut
  mit per-Feld-Fehlercodes (`invalid_number`, `out_of_range`); leere
  Felder lassen den gespeicherten Wert unverändert.

### Tests

- `benni_media_context`: 20 neue Tests in `test_orchestrator.py`
  (Priorität, PS5/Switch/PC-Gaming-Regeln, Apple-TV-System-App-Filter,
  Auto-Pause/Resume-Bookkeeping, Manual-Stop-Block, Bio-Sleep-Block,
  Radio-vs-Manual-Wahl, Debug-Surface).
- `test_tuning_decimal_separator.py`: Pinning auf den
  Step-Handler-Validierungspfad — Komma-/Dot-Submit, Out-of-range
  → `errors`-Rerender, Garbage → `invalid_number`, leeres Feld
  behält Storage-Wert, Regression auf bare `TextSelector` im Schema.
- Smoke-Test um die vier neuen Entity-Keys erweitert.
- Full suite: `613 passed, 2 warnings`.

### Kompatibilität

- Keine Migration nötig. Bestehende Sensor-/Binary-Sensor-Entities
  bleiben unverändert. Die neuen Orchestrator-Outputs erscheinen
  zusätzlich am bestehenden Device.

## 0.3.6.10 - 2026-05-25

### Geändert

- Benni Context: Bio-/Activity-Logik gegen die reviewed
  Lastenhefte abgeglichen.
- Bio-State:
  - `wake_needed` vom Wake Planner setzt `sleep` nur auf
    `waking`; echte Aktivitätsindikatoren setzen anschließend
    direkt auf `awake`.
  - Kaffee, Tür/Fenster-Wake-Signal, PC und PS5 wecken nur noch in
    Tagesphasen `early_morning`, `late_morning`, `forenoon`,
    `afternoon`, `early_evening`, `late_evening`.
  - `early_night`, `late_night` und fehlender Day-State blockieren
    diese Aktivitäts-Wake-Trigger konservativ.
  - `homeoffice` ist kein Wake-Trigger mehr; es bleibt ein
    Activity-Input.
  - Verlassen der Wohnung während `sleep`/`waking` erzwingt weiterhin
    `awake`.
- Activity-State:
  - `bio=sleep` wird jetzt als Activity `sleep` durchgereicht.
  - `bio=waking` wird jetzt als Activity `waking` durchgereicht.
  - Priorität ist jetzt: `sleep` > `waking` > `private_time` >
    `work_home` > `household` > `free_time` > `idle`.
  - `private_time` gewinnt vor `work_home`.
  - `work_away` wird nicht mehr allein aus `presence=abwesend`
    geraten; dafür braucht es später eine echte Arbeitsort-Quelle.

### Tests

- `benni_context`: 38 Tests (+1), darunter Regressionen für
  Activity-Wake bei Tag, Blockade bei Nacht/fehlendem Day-State,
  `homeoffice` ohne Wake-Wirkung, `sleep`/`waking` als Activity und
  `private_time` vor `work_home`.
- Full test suite at release preparation: `590 passed, 2 warnings`.

### Kompatibilität

- Keine `unique_id`-Änderungen.
- Keine CONF-Key-Renames.
- Keine Entity-Registry-Migration.
- Bestehende `benni_context`-Entries laufen weiter; die Änderung ist
  reine Entscheidungslogik.

## 0.3.6.9 - 2026-05-22

### Hinzugefügt

- Wake Planner: Neuer Binary Sensor pro Person
  `binary_sensor.wake_planner_<slug>_holiday_active`. Liefert den
  Feiertag/Frei-Tag-Boolean, den `benni_context.holiday_sensor`
  konsumiert, statt YAML-seitig den `decision.reason`-String zu
  parsen.
- Semantik:
  - `on`, wenn `decision.holiday_name` gesetzt ist **oder**
    `decision.matched_rule_id == "profile_holiday"`.
  - `off` für reguläre Werktage und Cold-Start (keine Decision).
- Attribute: `holiday_name`, `reason`, `decided_by`,
  `matched_rule_id`, `next_wake`, `wake_state`, `person_id`.
- Entity-Konvention:
  - `suggested_object_id = "wake_planner_<slug>_holiday_active"`
  - `unique_id = "bennis_toolbox_wake_planner_<entry_id>_<slug>_holiday_active"`
- Umbrella-Translations: DE „Feiertag aktiv" / EN „Holiday active".

### Tests

- Neuer `test_holiday_active.py` (11): Wahrheitstabelle für
  `holiday_name`, `matched_rule_id`, Werktag, fehlende Decision,
  leerer holiday_name; Attribute werden korrekt durchgereicht;
  Cold-Start ohne Decision liefert `{}`; `next_wake=None`
  handled; `suggested_object_id` + `unique_id` Pattern;
  Plattform-Dispatcher liefert pro Person beide Binary-Sensoren.
- wake_planner: 84 Tests (+11).
- Full test suite at release preparation: `584 passed, 2 warnings`.

### Kompatibilität

- Keine `unique_id`-Änderungen an bestehenden Wake-Planner-Entities.
- Keine Engine-Policy-Änderungen.
- Keine CONF-Key-Renames.
- Bestehende Setups: Beim Reload erscheint der neue Binary
  Sensor automatisch pro Person.

## 0.3.6.8 - 2026-05-22

### Behoben

- Benni Media Context: Im „Lautstärke & Debounce"-Step wurden
  Dezimalwerte in der deutschen HA-Locale mit Komma angezeigt
  (`0,15`, `-0,1`). Der Spec/Code-Konsens war jedoch
  Punkt-separierte Werte (`0.15`, `-0.1`). Ursache: HAs
  `NumberSelector` formatiert immer locale-spezifisch.
- Fix: Die sechs Tuning-Felder
  (`debounce_seconds`, `quiet_ducking_level`,
  `base_volume_homepods`, `base_volume_denon`,
  `track_boost_offset`, `window_volume_offset`) verwenden jetzt
  einen `TextSelector` plus eine Coercion-Kette `_to_decimal()` →
  `vol.Range`. Defaults werden über `_fmt_decimal()` mit Punkt
  gerendert. Beim Submit nehmen wir sowohl `"0.15"` als auch
  `"0,15"` an (für User, die im DE-Layout den Komma-Eintrag
  gewohnt sind) — beides landet konsistent als Python-Float in
  `entry.options`.

### Tests

- Neuer `test_tuning_decimal_separator.py` (13): Coercion akzeptiert
  Dot/Comma-Strings, Numbers, Whitespace, leere Inputs; lehnt
  Garbage ab; Defaults werden mit Punkt gerendert; alle 6
  Tuning-Felder nutzen `TextSelector`, nicht `NumberSelector`;
  Round-Trip von `"-0,1"` → `-0.1`; Range-Validierung nach der
  Coercion; bestehende `0.15`-Submission funktioniert weiterhin.
- benni_media_context: 140 Tests (+13).
- Full test suite at release preparation: `573 passed, 2 warnings`.

### Kompatibilität

- Keine `unique_id`-Änderungen, keine CONF-Key-Renames.
- Storage-Format unverändert; gespeicherte Floats bleiben Floats.
- Bestehende Setups sehen beim nächsten Öffnen des Tuning-Steps
  die Werte als Punkt-Strings — Einreichen schreibt wieder Float.

## 0.3.6.7 - 2026-05-22

### Behoben

- Title Classifier: Im Einhornzentrale-Setup war das `artist_attribute`
  beim Watcher-Anlegen auf `active_queue` gesetzt worden (Music
  Assistant exposed dort eine interne Queue-ID wie
  `syncgroup_edfgeqne`). Dadurch landeten **alle** Musik-Einträge im
  Panel als `syncgroup_edfgeqne - <Titel>` — die in 0.3.6.6
  eingeführte Fallback-Kette griff nicht, weil das konfigurierte
  Attribut immer Vorrang hat.
- Fix: Neue Heuristik `_looks_like_internal_id(value)` erkennt
  Music-Assistant-/Queue-IDs (`syncgroup_…`, `mass_…`,
  `ma_queue_…`, `queue_…`, `player_id_…`, `uuid:…`, `urn:…`),
  UUIDs (mit/ohne Bindestriche) und allgemein opaque Tokens
  (rein lowercase + Ziffern + Underscore/Hyphen, keine
  Whitespace/Slash/Punkt, Länge ≥ 6). Solche Werte werden auf
  jeder Stufe der Artist-Resolver-Kette übersprungen — auch wenn
  sie aus dem **konfigurierten** Attribut kommen. Echte Künstler
  („Becky Hill feat. Shift K3Y", „Daft Punk", „1LIVE", „WDR 4",
  „Jack FM - Berlin", „Pro7") passieren weiterhin.

### Tests

- `test_artist_resolution.py` (+7): Heuristik erkennt
  `syncgroup_*`, `mass_*`, UUIDs, generische lowercase-Tokens;
  echte Künstlernamen werden nicht abgelehnt; mis-configured
  `active_queue` fällt automatisch auf `media_artist` zurück
  („Better Off Without You" gruppiert jetzt unter „Becky Hill
  feat. Shift K3Y"); ohne valide Fallback-Quelle bleibt der
  Bare-Title statt einer Opaque-ID; auch der Radio-Station-
  Fallback lehnt opaque IDs ab.
- title_classifier: 51 Tests (+7).
- Full test suite at release preparation: `560 passed, 2 warnings`.

### Kompatibilität

- Keine `unique_id`-Änderungen, keine CONF-Key-Renames.
- Storage-Format unverändert; alte Einträge mit
  `syncgroup_*`-Prefix bleiben sichtbar (lassen sich im Panel per
  „Aufräumen" / `delete_entry`-Service entfernen). Neue
  State-Changes der Source-Entity erzeugen Einträge mit dem
  korrekten Artist.

## 0.3.6.6 - 2026-05-22

### Geändert

- Title Classifier: Artist-Auflösung deutlich robuster. Bisher wurde
  ausschließlich `media_artist` als Attribut gelesen — Music
  Assistant exposed den Wert aber unter `artist`. Resultat: Musik-
  Einträge im Panel ohne Künstler. Neuer Lookup-Pfad:
  1. konfiguriertes `CONF_ARTIST_ATTRIBUTE` (falls gesetzt),
  2. `ARTIST_ATTRIBUTE_CANDIDATES` (`media_artist`, `artist`,
     `media_album_artist`, `album_artist`) — der erste nicht-leere
     Wert gewinnt.
- Title Classifier (nur `media`-Watcher): Fällt der Track-Artist
  weg — typisch für Radio-Streams — wird ein „Synthetic-Artist" aus
  dem Sendernamen abgeleitet (`radio_station_name`, `media_station`,
  `station`, `channel`, `media_channel`). Dadurch landen Einträge
  wie „WDR 2 POP. Die Abendshow mit Marcus Barsch" unter „WDR 2
  Bergisches Land" und „1LIVE Fiehe" unter „1LIVE", statt
  zwischen den unklassifizierten Titeln zu verschwinden.
- `game`- und `activity`-Watcher nutzen den Radio-Fallback bewusst
  nicht — der gilt nur für Musik-Watcher.

### Tests

- Neuer `test_artist_resolution.py` (13): Music-Assistant-`artist`-
  Attribut funktioniert; klassisches `media_artist` weiterhin
  unterstützt; konfiguriertes Attribut hat Vorrang;
  `album_artist`-Fallback; Radio-Sender als Synthetic-Artist für
  Musik; bei vorhandenem Track-Artist gewinnt der über die Station;
  Alias-Attribute (`media_station`); leere/`unknown`-Werte werden
  gereinigt; `game`/`activity` ignorieren Radio-Fallback;
  Einhornzentrale-Repros (1LIVE Fiehe, WDR 2 POP, Time after time,
  Rondeau, Save My Love).
- title_classifier: 44 Tests (+13).
- Full test suite at release preparation: `553 passed, 2 warnings`.

### Kompatibilität

- Keine `unique_id`-Änderungen, keine CONF-Key-Renames.
- Bestehende Watcher mit explizitem `artist_attribute` verhalten
  sich unverändert.
- Storage-Format unverändert; bestehende Einträge bleiben gültig.

## 0.3.6.5 - 2026-05-22

### Behoben

- Benni Media Context: `device_diagnostics` blieb auf den
  `media_context`- und `media_device`-Sensoren dauerhaft `{}`,
  obwohl der Coordinator die Diagnose pro Geräte-Karte korrekt
  aufbaute. Ursache: das Feld lebte ausschließlich auf der
  `Snapshot`-Dataclass, die der Coordinator nicht publiziert. Die
  Entities lesen `coordinator.data.device_diagnostics` — aber
  `coordinator.data` ist eine `Decision`, und die Decision-Dataclass
  hatte das Feld bisher nicht. `getattr(..., "device_diagnostics",
  {})` lieferte deshalb immer den leeren Default.
- Fix: `Decision.device_diagnostics` als eigenes Feld; `decide()`
  kopiert `snap.device_diagnostics` in beide Rückgabe-Pfade
  (Quiet-Early-Return und Hauptpfad). Coordinator-Debounce-Interims
  übernehmen die frischen Diagnostics ebenfalls, damit die Attribute
  nicht stale werden, während der Context zwischen Stable-States
  hin- und herwechselt.
- Engine-Policy unverändert: `device_diagnostics` ist reines
  Beiwerk und beeinflusst weder `context` noch `device` noch
  `gaming_source`/`gaming_platform`.

### Tests

- Neuer `test_device_diagnostics_propagation.py` (9): pin
  Decision-Feld-Existenz; `decide()` kopiert Snapshot-Diag in beide
  Pfade; konfigurierte Cards füllen Diag auch wenn Gerät off ist;
  PC-Active-Repro liefert `pc`-Bucket mit `configured_*_entity` +
  `active_state` + `power_w` + `resolution_source=new_key`;
  Legacy-only-Setup markiert `legacy_fallback`; neuer Key gewinnt
  über Legacy in Runtime und Diag; beide Sensoren exposen das
  gleiche Diag-Dict.
- benni_media_context: 127 Tests (+9).
- Full test suite at release preparation: `540 passed, 2 warnings`.

### Kompatibilität

- Keine `unique_id`-Änderungen.
- Keine CONF-Key-Renames.
- Engine-Policy unverändert; `context`/`device`/`gaming_source`/
  `gaming_platform`/Subwoofer-Policy/Volume-Targets unverändert.
- Legacy-Read-Fallback bleibt aktiv für nicht migrierte Entries.

## 0.3.6.4 - 2026-05-22

### Behoben

- Benni Media Context: Der Legacy-Aggregat-Step „Auslöser & Quellen"
  erschien noch im normalen Options-Menü und führte beim Öffnen zur
  alten Maske mit `tv_active`, `tv_source`, `tv_power_fallback`,
  `appletv`, `ps5_status`, `switch_dock` etc. Der Step ist jetzt
  gegated: er erscheint **nur**, wenn der Entry tatsächlich
  Legacy-CONF-Werte in `entry.data` oder `entry.options` enthält
  (Migrationsfall). Frische Entries sehen die Karte gar nicht mehr.
- Benni Media Context: Wenn der Step doch erscheint, ist er klar als
  „Legacy-Quellen (Altbestand)" / „Legacy sources (existing setups)"
  beschriftet — keine Verwechslungsgefahr mit der normalen
  Konfiguration über die Geräte-Karten.

### Hinzugefügt

- Coordinator: neuer Resolver `_resolve_with_origin(new_key)` liefert
  zusätzlich, ob die Entity über den neuen oder den Legacy-Key
  aufgelöst wurde.
- Snapshot `device_diagnostics` enthält jetzt pro Gerät:
  `configured_player_entity`, `configured_active_entity`,
  `configured_power_entity`, `configured_title_entity`,
  `configured_ping_entity` / `configured_network_entity` (je nach
  Karte), `resolution_source` (`"new_key"` oder `"legacy_fallback"`)
  und `resolution_per_role` (Detail pro Rolle).
- `sensor.benni_media_context_media_context` und
  `sensor.benni_media_context_media_device` legen `device_diagnostics`
  als Attribut frei — sichtbar in Lovelace und im Entity-Tab, ohne
  dass eine extra Entity-Registry aufgemacht wird.

### Tests

- Neuer `test_legacy_gating_and_diagnostics.py` (9): Frische Entries
  zeigen keinen `sources`-Step; Entries mit Legacy-Werten in `data`
  oder `options` zeigen ihn; reine Neu-Key-Setups verbergen ihn;
  Translation-Label enthält explizit „Legacy"/„Altbestand"; pro
  Gerät `configured_*_entity` + `resolution_source` korrekt; neuer
  Key gewinnt gegen Legacy-Fallback; Denon-`source` aus dem
  Player-Attribut, niemals als Power-Sensor-Entity-ID.
- Zwei bestehende Menü-Tests an die Gating-Semantik angepasst.
- benni_media_context: 118 Tests (+9).
- Full test suite at release preparation: `531 passed, 2 warnings`.

### Kompatibilität

- Keine `unique_id`-Änderungen.
- Keine CONF-Key-Renames.
- Engine-Policy unverändert.
- Legacy-Read-Fallback im Coordinator bleibt aktiv (alte
  Installationen laufen weiter).
- Keine Top-Level-Entity-Registry-Änderungen — die Diagnose liegt als
  Attribut auf zwei bestehenden Sensoren.

## 0.3.6.3 - 2026-05-22

### Behoben

- Benni Media Context: Beim Anlegen einer neuen Instanz erschien noch
  die alte Legacy-Erstkonfigurationsmaske mit Feldern wie `tv_active`,
  `tv_source`, `tv_power_fallback`, `appletv`, `ps5_status`,
  `switch_dock`. Erst nach leerem Bestätigen kam man in den neuen
  Options-Flow mit den Geräte-Karten. Der ConfigFlow zeigt jetzt ein
  leeres Welcome-Formular — der Nutzer klickt Submit und landet
  direkt auf dem neuen Options-Menü mit den Geräte-Karten.
- Benni Media Context: `denon_source` konnte fälschlich beim Lesen
  durch den Legacy-Fallback (`denon_active` mit einer Power-Binary
  ohne `source`-Attribut) als Quelle gemeldet werden. Wenn
  `denon_player_entity` konfiguriert ist, liest der Coordinator
  jetzt ausschließlich das `source`-Attribut dieses
  `media_player` — der Legacy-Slot kann den Wert nicht mehr
  überschreiben. Ohne neuen Player bleibt der bisherige Fallback
  auf das Source-Attribut des Legacy-Slots aktiv (deckt User ab, die
  einen `media_player` in den alten `denon_active`-Slot gehängt
  hatten).

### Tests

- `test_config_flow_minimal.py` (4): Welcome-Form ist leer; keine
  Legacy-Felder leaken; Submit erzeugt sofort einen Entry mit nur
  dem Modul-Identifier; Options-Menü zeigt weiterhin alle Karten.
- `test_denon_source_resolution.py` (5): `denon_source` kommt aus
  dem Player-Attribut; Fallback auf Legacy-Slot funktioniert ohne
  neuen Player; Power-Binary ohne `source`-Attribut liefert `None`,
  nie eine Entity-ID; neuer Player gewinnt über Legacy-Slot.
- benni_media_context: 109 Tests (+9).
- Full test suite at release preparation: `522 passed, 2 warnings`.

### Kompatibilität

- Keine CONF-Key-Renames, keine `unique_id`-Änderungen.
- Engine-Policy unverändert.
- Legacy-Step „Auslöser & Quellen" bleibt für Backwards-Compat im
  Options-Menü verfügbar.
- Bestehende Entries mit Legacy-Daten in `entry.data` laden
  unverändert.

## 0.3.6.2 - 2026-05-22

### Behoben

- Benni Media Context: Die neuen Geräte-Karten im Options-Menü hatten
  leere Labels — im UI sah man nur Chevron-Zeilen ohne Text. Die
  Karten-Titel und Menü-Labels (TV / Apple TV / PlayStation 5 /
  Nintendo Switch / PC / Denon / HomePods / Context / Legacy:
  Auslöser & Quellen / Lautstärke & Debounce) liegen jetzt in der
  Umbrella-`de.json`/`en.json` statt nur in den Modul-Translations.
- Benni Media Context: Die Entity-Dropdowns in den Karten zeigten
  alle Entities. Jedes Feld bekommt jetzt einen Domain-Filter
  passend zur fachlichen Rolle: `*_player_entity` → `media_player`,
  `*_active_entity` → `binary_sensor`, `*_power_entity` /
  `*_title_entity` → `sensor`, `*_ping_entity` / `*_network_entity`
  → `[binary_sensor, device_tracker]`. Context-Karte: `day_state` /
  `activity_state` → `sensor`, `window_state` / `entry_door` /
  `call_monitor` → `binary_sensor`.
- Benni Media Context: Wording in den Karten ist konsistent
  rollennamenbasiert. Legacy-Keys (`tv_active`, `ps5_status`,
  `switch_dock`, `homepods` etc.) tauchen NUR noch im
  Legacy-Aggregate-Step („Auslöser & Quellen") auf, niemals in den
  neuen Karten.

### Hinzugefügt

- Neue Options-Karte `context` für Globale Quellen (Tagesphase,
  Aktivität, Fenster, Tür, Anruf) mit domänspezifischen Selektoren,
  Skip/OK-Semantik analog zu den Geräte-Karten.

### Tests

- Neuer `test_options_ux_labels.py`: pin Translation-Labels für
  jedes Menü-Item, jeden Step-Titel und jede Feldbeschriftung in
  beiden Locales; keine Legacy-Namen in den neuen Karten;
  Domain-Filter je Feld korrekt; Context-Karte rendert genau ihre
  fünf Keys mit den richtigen Domains; Skip/OK-Verhalten bleibt
  unverändert.
- benni_media_context: 100 Tests (+30).
- Full test suite at release preparation: `513 passed, 2 warnings`.

### Kompatibilität

- Keine unique_id-Änderungen.
- Keine CONF-Key-Änderungen, neue Karten speichern weiterhin nur
  neue Keys; Legacy-Step bleibt unverändert verfügbar.

## 0.3.6.1 - 2026-05-22

### Behoben

- Benni Media Context: Coordinator-Setup brach mit
  `TypeError: cannot use 'list' as a dict key (unhashable type: 'list')`
  ab, sobald ein bestehender Eintrag einen list-förmigen Wert
  enthielt (z. B. die Legacy-`homepods`-Mehrfachauswahl). Der
  Tracker hat den list-Wert in seine Sammelliste aufgenommen und
  beim Dedupe mit `dict.fromkeys()` gecrashed. Neue Helper
  `_flatten_entities()` und `_first_entity()` akzeptieren jetzt
  None / String / list / tuple / set, flachen eine Ebene tief und
  liefern eine geordnete Stringliste. `_entity()` collapsed
  list-Legacy-Werte auf den ersten gültigen String, `_entities_list()`
  und das Setup-Dedupe nutzen den Flattener.
- Title Classifier Panel: Sidebar-Registrierung loggt nach Reload
  keinen „Overwriting panel"-Warning mehr. Static-Path-
  Duplikat-Registrierung wird sauber abgefangen; ein vorhandener
  Panel-Eintrag wird vor der Re-Registrierung über
  `frontend.async_remove_panel` entfernt. Gleicher Fix für das
  Wake-Planner-Panel.

### Tests

- Neuer `test_entity_flattening.py` (11): None/String/List/Tuple/Set
  Inputs, nested-list-Flattening, Whitespace-Trim, Drop von
  None/Empty/Duplikaten, Single-Entity-Collapse aus list-Legacy-
  Werten, Regression auf das exakte Crash-Szenario.
- benni_media_context: 70 Tests (+11).
- Full test suite at release preparation: `483 passed, 2 warnings`.

### Kompatibilität

- Keine unique_id-Änderungen.
- Keine CONF-Key-Änderungen.
- Bestehende Entries mit Legacy-list-Werten laden jetzt ohne
  Migration; die Werte werden für Single-Slot-Lesezugriffe auf
  den ersten gültigen Eintrag kollabiert.

## 0.3.6 - 2026-05-22

### Geändert

- Benni Media Context: Source-/Device-Modell auf media_player-Attribute
  umgestellt. Statt für jeden Detailwert (source, app, title) eine
  eigene Entity zu pflegen, liefert ein einziger media_player pro
  Gerät seinen `source`/`app_name`/`media_title`/`media_content_type`/
  `volume_level`. Die Active-/Power-/Ping-Slots sind nur noch
  optionale Plausibilitätssignale.
- Benni Media Context: Options-Flow erhält pro Gerät eine Karte —
  TV, Apple TV, PS5, Switch, PC, Denon, HomePods. Jede Karte zeigt
  nur die Slots dieses Geräts; Speichern berührt ausschließlich
  diese Keys. „Skip" ist implizit: Karte nicht öffnen oder leer
  abschicken → bestehende Werte bleiben unangetastet. Geleerte
  Slots werden aus options gestrichen, damit Legacy-Werte aus
  entry.data wieder durchgreifen.
- Coordinator: Resolver `_entity_with_fallback(new_key)` versucht
  erst die neue CONF-Adresse, fällt sonst auf den Legacy-Key
  zurück. Damit funktionieren existierende Config-Entries ohne
  Migration weiter (Backwards Compatibility ohne Touch von
  entry.data / unique_id).
- Denon-Audio-Path: kombiniert jetzt explizit `denon_player_entity`
  state + `source`-Attribut mit der `denon_active_entity`-Binary
  und dem Power-Sensor.
- Switch handheld_candidate: ping_on + dock_active=False +
  power_w<1.0 wird als Snapshot-Flag erfasst und als
  Diagnose-Reason im Switch-Device-Diagnostic-Dict gemeldet — kein
  dominanter Kontext, nur Hinweis.

### Hinzugefügt

- Snapshot trägt `device_diagnostics` mit pro Gerät:
  `player_state`, `active_state`, `power_w`, `network_state`,
  `source`, `app_name`, `media_title`, `content_type`, `volume_level`,
  `reasons`. Diese werden vom Coordinator gefüllt und stehen
  Entitäten als Attribut zur Verfügung.
- Neue CONF-Keys pro Gerät:
  `<device>_player_entity`, `<device>_active_entity`,
  `<device>_power_entity`, `<device>_network_entity` /
  `<device>_ping_entity`, `<device>_title_entity` (PS5).
- Translations (de/en) für alle Device-Karten.

### Tests

- `test_device_cards.py`: parametrisierte Tests pro Karte, die das
  Schema auf genau die Device-Keys einschränken; Submit einer Karte
  überschreibt keine anderen Geräte oder Tuning-Optionen; leerer
  Submit löscht nichts; Slot-Clear droppt den Key, damit Legacy-Werte
  durchgreifen.
- Bestehender Options-Menü-Test um die sieben neuen Geräte-Steps
  erweitert.
- benni_media_context: 59 Tests (+10 neu).
- Full test suite at release preparation: `472 passed, 2 warnings`.

### Kompatibilität

- Keine unique_id-Änderungen.
- Keine CONF-Key-Renames — alle alten Keys (`tv_active`, `appletv`,
  `ps5_status`, `ps5_title`, `switch_dock`, `pc_active`,
  `denon_active`, `homepods`) bleiben gültige Fallbacks für nicht
  migrierte Entries.
- enable_control / Subwoofer-Policy / Volume-Targets unverändert.

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
