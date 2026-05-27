# CLAUDE.md — Briefing für neue Sessions

**Letzte Aktualisierung:** 2026-05-27

---

## Was ist dieses Repo?

HACS-Custom-Integration `bennis_toolbox` für Home Assistant. Nach **Hybrid-Pivot (2026-05-27)** ist dieses Repo nur noch die **Foundation-Umbrella**:

- 3 Herzen: `benni_core_day_state`, `benni_core_user_state`, `benni_core_presence_state` (alle READY)
- Geplant: `benni_core_devices` (Atomic Layer)
- Legacy: `benni_context` (bleibt bis komplette Migration)
- Utilities: `storage.py`, `services.py`, `_platform_dispatch.py`, `config_flow.py`, `base.py`, `const.py`

Alle anderen früheren Module (`title_classifier`, `wake_planner`, `stash_ha`, `notification_router`, `maw`, `plug_policy_engine`, `cover_policy`, `benni_media_context`) werden von Codex schrittweise in **eigene Custom-Repos** extrahiert. Siehe `einhornzentrale/docs/roadmap.md`.

## Architektur-Pattern

- **Decision vs. Apply:** Toolbox-Module liefern Wahrheiten + Plans als HA-Sensoren. YAML in `einhornzentrale` applied.
- **Pure Logic isoliert:** Jedes Modul hat `logic.py` ohne HA-Imports, vollständig pytest-testbar.
- **Coordinator als HA-Brücke:** Hält Storage, Listener, Timer. Compute lebt in `logic.py`.
- **Single-Instance Config Flow** bei Foundation-Modulen.
- **Storage-Pattern:** über `make_store(hass, module_id, suffix)` aus `storage.py`. Storage-Key automatisch präfixiert.

## Wichtige Konventionen

- **Modul-Namen flach unter `modules/`**, keine nested Sub-Packages (siehe `memory/toolbox_rebuild_plan.md`)
- **Entity-Namespace** mit `benni_core_*` Prefix für neue Module
- **unique_id-Pattern:** `unique_id(module_id, entry_id, suffix)`
- **Services:** `bennis_toolbox.<module>_<action>` via ServiceDef in `services_impl.py`
- **Strukturelle Tests** in `tests/test_repo_structure.py` checken jedes Modul automatisch (Spec lädt HA-frei, keine Cross-Modul-Imports, EXPECTED_MODULE_IDS gepflegt)

## Extraction Lessons — title_classifier Pilot (2026-05-27)

- Standalone-Zielname konsequent `title_classifier`; alter Repo-/Domain-Name `etm` wurde komplett entfernt.
- Toolbox-Imports waren gebündelt in `const`, `storage`, `services`, Panel-/WebSocket-Helpern und Unique-ID-Helpern; dafür braucht das Zielrepo eigene Root-Adapter.
- Für Standalone-HA braucht das Zielrepo einen echten `__init__.py`-Dispatcher: Services/WebSockets registrieren, `sensor`/`number` forwarden, Panel lazy registrieren.
- Frontend-WebSocket-Strings müssen zusammen mit `websocket_type()` umgestellt werden.
- Tests ließen sich übernehmen; nötig waren nur Package-Pfad und Storage-Helper-Stub.
- Migration-sensitive Stellen: Service-Domain, WebSocket-Namespace, Storage-Key und unique_id-Prefix vor Cut-over explizit dokumentieren.

## Verwandte Repos

| Repo | Rolle |
|---|---|
| `D:\Dokumente\GitHub\einhornzentrale` | YAML-Konsument. **Wichtig:** dort `CLAUDE.md` lesen für Cut-Over-Status, Disziplin-Regeln, Architektur-Roadmap |
| `haos_benni` | Alte produktive VM. Wird NICHT mehr angefasst (nur Hotfixes). |
| `ha_wake_planner`, `Entity-Title-Mapper`, `stash-ha`, `benni_notification_router`, `benni_plug_policy`, `benni_media_context`, `Media_Art_Wrapper` | Eigene Modul-Repos — werden via Codex-Extraction gefüllt |

## Memory-Files (`~/.claude/projects/.../memory/`)

- `MEMORY.md` — Index
- `repo_topology.md` — Wo welcher Code lebt
- `lastenheft_source.md` — Welche Lastenhefte führend (Quelle: `einhornzentrale/docs/lastenhefte/reviewed/`)
- `toolbox_rebuild_plan.md` — Architektur-Entscheidungen
- `codex_role.md` — Was Codex tut/nicht tut
- `user_profile.md` — Über Benjamin

## Wenn du in einer neuen Session startest

1. **Lies das hier zuerst.**
2. **Lies `einhornzentrale/CLAUDE.md`** (im anderen Repo) für Cut-Over-Status und nächste Schritte.
3. **Lies Memory-Files** für Architektur-Entscheidungen.
4. **Bei Modul-Bau:** Pattern aus `benni_core_user_state/` oder `benni_core_presence_state/` übernehmen — gut etabliert, vollständig getestet.

## Anti-Patterns

- ❌ Cross-Modul-Imports (`from ..benni_context import ...`) — strukturelle Tests fangen das
- ❌ HA-Imports in `logic.py` — sonst nicht pytest-testbar
- ❌ Direkte Service-Calls aus Modulen die produktive Geräte schalten — Decision/Apply-Trennung
- ❌ Neue Module ohne `_spec.py` mit `ModuleStatus` — Registry findet sie nicht
- ❌ Cover_policy / Light / Klima neu in dieses Repo bauen — gehören in eigene Repos (Hybrid-Pivot)
