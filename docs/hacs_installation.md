# HACS-Installation

## Voraussetzungen

- Home Assistant 2024.10.0 oder neuer
- HACS installiert und eingerichtet

## Schritte

1. **HACS → Custom Repositories**
2. URL `https://github.com/Levtos/bennis_toolbox`, Kategorie **Integration**
3. „Benni's Toolbox" in der HACS-Liste auswählen → **Download**
4. **Home Assistant neu starten**

Nach dem Neustart liegt unter `/config/custom_components/` ausschließlich:

```
/config/custom_components/bennis_toolbox/
```

Keine weiteren Top-Level-Ordner. Das ist Absicht — Sub-Module wohnen
unter `bennis_toolbox/modules/<id>/` und sind keine eigenen
HA-Integrationen.

## Toolbox + Modul hinzufügen

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. „Benni's Toolbox" auswählen
3. Modul aus der Liste wählen (z. B. „Title Classifier")
4. Modul-spezifische Schritte durchlaufen, falls vorhanden

Für **mehrere Instanzen** eines Moduls (z. B. zwei MAW-Player) den
Schritt einfach erneut durchlaufen — jede Instanz wird ein eigener
Config-Entry.

## Verifikation auf HAOS

```bash
# auf der HAOS-VM
ls -la /config/custom_components
# Erwartet (neben hacs / spook / …):
# bennis_toolbox
```

und in HA selbst:

```yaml
# Entwicklerwerkzeuge → Zustand → Filter
domain: bennis_toolbox
```

zeigt die Toolbox-Entries und die durch READY-Module erzeugten Entities.

## Bekannte Einschränkungen Stand 0.2.0

- Phase-1-Module stehen auf `PENDING`. Sie können in der UI ausgewählt
  und als Entry angelegt werden, registrieren aber noch keine Entities
  oder Services, bis ihre Fachlogik aus `_reference/` portiert ist
  (siehe `docs/module_adapter.md`).
- `maw` und `stash_ha` sind `STUB` und vorerst rein deklarativ.

## Update

Über HACS — die Toolbox bekommt ein neues Release, HACS bietet das
Update an. HA neu starten. Bestehende Config-Entries bleiben erhalten,
ihr `_module_id` wird respektiert.
