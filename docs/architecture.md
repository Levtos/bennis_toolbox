# Architektur

## Zielbild

`bennis_toolbox` ist ein **Monorepo** und die alleinige **Source of Truth**
für alle enthaltenen Custom Integrations. Es bündelt sie nur logisch und
für HACS-Verteilung, **nicht** funktional zu einer Mega-Integration. Die
historischen Einzel-Repos sind deprecated.

Tests aller Teilintegrationen leben unter [`tests/`](../tests/) im Monorepo
und werden mit `pytest tests/` als Ganzes ausgeführt.

```
custom_components/
  bennis_toolbox/         # Dach: Übersicht, Health, Diagnose
  wake_planner/
  title_classifier/       # ehem. etm
  benni_context/
  benni_media_context/
  notification_router/    # ehem. benni_notification_router
  plug_policy_engine/     # ehem. benni_plug_policy
  stash_ha/               # ehem. stash_player
  maw/                    # ehem. media_art_wrapper
```

## Finale Domain-Liste

| Domain                | Anzeigename            |
| --------------------- | ---------------------- |
| `bennis_toolbox`      | Benni's Toolbox        |
| `wake_planner`        | Wake Planner           |
| `title_classifier`    | Title Classifier       |
| `benni_context`       | Benni Context          |
| `benni_media_context` | Benni Media Context    |
| `notification_router` | Notification Router    |
| `plug_policy_engine`  | Plug Policy Engine     |
| `stash_ha`            | Stash HA               |
| `maw`                 | Media Art Wrapper      |

Geschichte der Umbenennung siehe [migration.md](migration.md).

## Schichten

| Schicht                | Wer            | Erlaubt                                     | Verboten                       |
| ---------------------- | -------------- | ------------------------------------------- | ------------------------------ |
| Fachschicht            | Teilintegrationen | Eigene Domain, eigene Entities, eigene Logik | Cross-Imports anderer Teile    |
| Dach-/Observerschicht  | `bennis_toolbox` | Statusabfrage über `homeassistant.loader`, `config_entries.async_entries(domain)`, Diagnostics, Health-Sensoren, Navigation, Legacy-Domain-Erkennung als Warnhinweis | Fachliche Entscheidungen, Automationen, harte Imports der Teile, automatische Migration |

## Entkopplungsregeln

1. **Keine harten Imports** zwischen Teilintegrationen — auch nicht von der
   Toolbox aus. Die Toolbox liest ausschließlich öffentliche HA-APIs
   (`async_get_integration`, `config_entries`, `states`).
2. **Keine geteilten Storage-Keys.** Wenn gemeinsame Helpers nötig werden,
   wandern sie nach `custom_components/bennis_toolbox/_shared/` und sind
   reine Funktionen ohne State.
3. **Jede Teilintegration bleibt einzeln installierbar.** Wer nur
   `wake_planner` will, kopiert ausschließlich diesen Ordner.
4. **Dach kennt Teile, Teile kennen Dach nicht.** Die Liste der Member steht
   in `bennis_toolbox/const.py:KNOWN_MEMBERS`. Teilintegrationen
   importieren das nie.
5. **Legacy-Domains nie als Zielnamen.** `LEGACY_DOMAINS` in
   `bennis_toolbox/const.py` dient ausschließlich der Erkennung
   versehentlich verbliebener Alt-Config-Entries und produziert nur
   Hinweise — keine Migration, keine doppelte Anzeige.

## Health-Modell

Die Toolbox erzeugt:

- 1 Overall-Sensor `sensor.bennis_toolbox_status` → `"<healthy>/<total> healthy"`,
  Attribut `members` listet alle Module mit Detailstatus.
- 1 Sensor je bekannter (finaler) Teilintegration. Werte:
  `healthy | warning | not_loaded | missing | unknown`. `warning` z. B.
  wenn ein Legacy-Config-Entry erkannt wurde.

Erkennung läuft über `async_get_integration` (installiert?) und
`hass.config_entries.async_entries(domain)` (konfiguriert/geladen?).

## Wiederverwendbarkeit für `parents_toolbox`

Das Muster (Dach mit `KNOWN_MEMBERS` + `LEGACY_DOMAINS` + `status.py` +
Health-Sensor + Diagnostics) ist generisch. Für `parents_toolbox` reicht
es, das `bennis_toolbox/`-Verzeichnis zu klonen, `DOMAIN` /
`KNOWN_MEMBERS` zu ersetzen und neue Teilintegrationen daneben zu legen.
