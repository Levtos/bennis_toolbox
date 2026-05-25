"""DataUpdateCoordinator für Benni Media Context.

Event-driven: hört auf alle konfigurierten Quell-Entities und triggert
`async_recalculate` per Debounce. Die fachliche Logik liegt in `logic.py`
als reine Funktion `decide(snap, ...)` und ist HA-frei.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...const import DATA_ENTRIES, DOMAIN
from .const import (
    BIO_SLEEP_VALUES,
    CONF_ACTIVITY_STATE,
    CONF_APPLETV,
    CONF_BIO_STATE,
    CONF_MANUAL_PLAYBACK,
    CONF_MEDIA_STOP_LATCH,
    CONF_OPENING_ANY_OPEN,
    CONF_PC_GAMING_ACTIVE,
    CONF_PLANNED_RADIO,
    CONF_QUIET_MODE_ENTITY,
    CONF_VOL_ACTIVE_MIN,
    CONF_VOL_DENON_BASE,
    CONF_VOL_DENON_MAX,
    CONF_VOL_DUCKED_TARGET,
    CONF_VOL_EDGE_DAY_OFFSET,
    CONF_VOL_HOMEPODS_BASE,
    CONF_VOL_HOMEPODS_MAX,
    CONF_VOL_NIGHT_OFFSET,
    CONF_VOL_OPENING_OFFSET,
    DEFAULT_VOL_ACTIVE_MIN,
    DEFAULT_VOL_DENON_BASE,
    DEFAULT_VOL_DENON_MAX,
    DEFAULT_VOL_DUCKED_TARGET,
    DEFAULT_VOL_EDGE_DAY_OFFSET,
    DEFAULT_VOL_HOMEPODS_BASE,
    DEFAULT_VOL_HOMEPODS_MAX,
    DEFAULT_VOL_NIGHT_OFFSET,
    DEFAULT_VOL_OPENING_OFFSET,
    ORCH_INPUTS,
    ORCH_REQUIRED_INPUTS,
    VOL_PRIMARY_INPUTS,
    CONF_APPLETV_APP_MAP,
    CONF_BASE_VOL_DENON,
    CONF_BASE_VOL_HOMEPODS,
    CONF_BOOST_OFFSET,
    CONF_CALL_MONITOR,
    CONF_DAY_STATE,
    CONF_DEBOUNCE,
    CONF_DENON_ACTIVE,
    CONF_DOOR,
    CONF_HOMEPODS,
    CONF_PC_ACTIVE,
    CONF_PS5_STATUS,
    CONF_PS5_TITLE,
    CONF_QUIET_DUCK,
    CONF_SWITCH_DOCK,
    CONF_TITLE_CLASSIFIER_HOMEPODS,
    CONF_TITLE_CLASSIFIER_MEDIA,
    CONF_TITLE_CLASSIFIER_PC,
    CONF_TITLE_CLASSIFIER_PS5,
    CONF_TV_ACTIVE,
    CONF_TV_POWER_FALLBACK,
    CONF_TV_SOURCE,
    CONF_WINDOW_OFFSET,
    CONF_WINDOW_STATE,
    CONF_TV_PLAYER, CONF_TV_ACTIVE_NEW, CONF_TV_POWER,
    CONF_APPLETV_PLAYER,
    CONF_PS5_PLAYER, CONF_PS5_ACTIVE, CONF_PS5_POWER,
    CONF_PS5_TITLE_ENTITY, CONF_PS5_NETWORK,
    CONF_SWITCH_ACTIVE, CONF_SWITCH_POWER, CONF_SWITCH_PING,
    CONF_PC_ACTIVE_NEW, CONF_PC_POWER,
    CONF_DENON_PLAYER, CONF_DENON_ACTIVE_NEW, CONF_DENON_POWER,
    CONF_HOMEPODS_PLAYER,
    DEVICE_CARDS, LEGACY_FALLBACKS,
    CTX_STREAMING,
    DEFAULT_APPLETV_APP_MAP,
    DEFAULT_BASE_VOL_DENON,
    DEFAULT_BASE_VOL_HOMEPODS,
    DEFAULT_BOOST_OFFSET,
    DEFAULT_DEBOUNCE,
    DEFAULT_QUIET_DUCK,
    DEFAULT_WINDOW_OFFSET,
    MODULE_ID,
)
from .logic import Decision, Snapshot, decide
from .orchestrator import (
    OrchestratorDecision,
    OrchestratorState,
    decide_audio_orchestrator,
)
from .volume_orchestrator import (
    VolumeDecision,
    VolumeSettings,
    decide_volume,
)

_LOGGER = logging.getLogger(__name__)


def _flatten_entities(value: Any) -> list[str]:
    """Normalise any CONF value into a flat ordered list of entity_ids.

    Accepts:
    - None / "" → []
    - str → [str]
    - list / tuple / set → flattened one level (nested lists handled)
    Drops empty strings, None, and any non-string after flattening.
    Preserves insertion order via dict-key uniqueness.
    """
    if value in (None, "", [], (), set()):
        return []
    out: list[str] = []

    def _walk(v):
        if v in (None, ""):
            return
        if isinstance(v, str):
            s = v.strip()
            if s:
                out.append(s)
            return
        if isinstance(v, (list, tuple, set, frozenset)):
            for item in v:
                _walk(item)
            return
        # Fallback for unexpected types — coerce to str, drop if empty.
        try:
            s = str(v).strip()
        except Exception:
            return
        if s and s.lower() not in ("none", ""):
            out.append(s)

    _walk(value)
    # Ordered dedupe.
    return list(dict.fromkeys(out))


def _first_entity(value: Any) -> Optional[str]:
    """Return the first valid entity_id from a (potentially list-shaped)
    CONF value, or None. Used for slots the new model treats as
    single-entity but where a legacy entry might have stored a list."""
    flat = _flatten_entities(value)
    return flat[0] if flat else None


def _bool_state(v: Optional[str]) -> bool:
    if v is None:
        return False
    return str(v).lower() in (
        "on", "true", "1", "active", "open", "playing", "home", "detected",
    )


def _maybe_int(v: Optional[str], default: int = 0) -> int:
    if v is None or v in ("unknown", "unavailable", "none", ""):
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class BenniMediaCoordinator(DataUpdateCoordinator[Decision]):
    """Coordinator. Event-driven; recomputes whenever a tracked entity changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{MODULE_ID}_{entry.entry_id}",
            update_interval=None,  # event driven
        )
        self.entry = entry
        self._unsub_state = None

        # Session-persistent state
        self._pre_atv_scenario: Optional[Decision] = None
        self._last_stable: Decision = Decision()
        self._pending_decision: Optional[Decision] = None
        self._pending_since: float = 0.0
        self._manual_nudge: Optional[str] = None
        # Audio orchestrator persistent state. Updated only on _commit so
        # debounce-driven recomputes don't double-consume transitions.
        self._orch_state: OrchestratorState = OrchestratorState()

        self.data = Decision()
        self._last_snapshot: Optional[Snapshot] = None

    # -- options helpers --
    def _opt(self, key: str, default: Any) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    def _entity(self, key: str) -> Optional[str]:
        """Return ONE entity_id for the given CONF key.

        Tolerant of legacy storage shapes — older entries may have
        persisted a list (e.g. `homepods`) even for slots that the new
        model treats as a single media_player. We collapse to the first
        valid string and ignore None/empty noise so callers can pass
        the return value into `hass.states.get(...)` or a hash set
        without crashing.
        """
        v = self.entry.options.get(key)
        if v in (None, ""):
            v = self.entry.data.get(key)
        return _first_entity(v)

    def _entities_list(self, key: str) -> list[str]:
        v = self.entry.options.get(key)
        if not v:
            v = self.entry.data.get(key)
        return _flatten_entities(v)

    def _entity_with_fallback(self, new_key: str) -> Optional[str]:
        """Resolve an entity slot using the new CONF model, falling back
        to the matching legacy key for unmigrated config entries."""
        eid = self._entity(new_key)
        if eid:
            return eid
        legacy = LEGACY_FALLBACKS.get(new_key)
        if legacy:
            return self._entity(legacy)
        return None

    def _resolve_with_origin(self, new_key: str) -> tuple[Optional[str], Optional[str]]:
        """Like ``_entity_with_fallback`` but also returns whether the
        entity came from the new key or the legacy fallback.

        Returns ``(entity_id, origin)`` where origin is ``"new_key"``,
        ``"legacy_fallback"`` or ``None`` when no entity is configured.
        """
        eid = self._entity(new_key)
        if eid:
            return eid, "new_key"
        legacy = LEGACY_FALLBACKS.get(new_key)
        if legacy:
            leid = self._entity(legacy)
            if leid:
                return leid, "legacy_fallback"
        return None, None

    def _app_map(self) -> dict[str, str]:
        # App map currently has no UX surface, but follow the same
        # merge pattern so a future options-step can override.
        return (
            self.entry.options.get(CONF_APPLETV_APP_MAP)
            or self.entry.data.get(CONF_APPLETV_APP_MAP, DEFAULT_APPLETV_APP_MAP)
        )

    # -- lifecycle --
    async def async_setup(self) -> None:
        entities: list[str] = []
        # Walk every device card so newly configured slots get tracked
        # alongside the legacy keys.
        for keys in DEVICE_CARDS.values():
            for k in keys:
                e = self._entity_with_fallback(k)
                if e:
                    entities.append(e)
        # Context / classifier / window / door / call etc. still use
        # their original keys. The orchestrator inputs
        # (bio/manual_playback/planned_radio + the 0.3.8 additions:
        # pc_gaming_active, media_stop_latch, opening_any_open,
        # quiet_mode) ride along here.
        for key in (
            CONF_TV_SOURCE,
            CONF_TITLE_CLASSIFIER_PS5, CONF_TITLE_CLASSIFIER_PC,
            CONF_TITLE_CLASSIFIER_HOMEPODS, CONF_TITLE_CLASSIFIER_MEDIA,
            CONF_DOOR, CONF_CALL_MONITOR, CONF_DAY_STATE,
            CONF_ACTIVITY_STATE, CONF_WINDOW_STATE,
            CONF_BIO_STATE, CONF_MANUAL_PLAYBACK, CONF_PLANNED_RADIO,
            CONF_PC_GAMING_ACTIVE, CONF_MEDIA_STOP_LATCH,
            CONF_OPENING_ANY_OPEN, CONF_QUIET_MODE_ENTITY,
        ):
            e = self._entity(key)
            if e:
                entities.append(e)
        # Legacy multi-homepods list — only relevant if no
        # CONF_HOMEPODS_PLAYER is configured.
        if not self._entity(CONF_HOMEPODS_PLAYER):
            for e in self._entities_list(CONF_HOMEPODS):
                entities.append(e)
        # Robust dedupe: legacy entries may have stored a list under a
        # nominally-single key, or a slot that resolved to None slipped
        # in. `_flatten_entities` accepts any shape and returns a clean
        # ordered list of strings.
        entities = _flatten_entities(entities)

        if entities:
            self._unsub_state = async_track_state_change_event(
                self.hass, entities, self._handle_state_event
            )
        await self.async_recalculate()

    async def async_unload(self) -> None:
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None

    # -- state change handler --
    @callback
    def _handle_state_event(self, event: Event) -> None:
        self.hass.async_create_task(self.async_recalculate())

    # -- snapshot construction --
    def _build_snapshot(self) -> Snapshot:
        hass = self.hass
        s = Snapshot()

        def _state(key: str) -> Optional[str]:
            ent = self._entity(key)
            if not ent:
                return None
            st = hass.states.get(ent)
            if st is None or st.state in ("unavailable", "unknown"):
                return None
            return st.state

        def _attr(key: str, attr: str) -> Optional[str]:
            ent = self._entity(key)
            if not ent:
                return None
            st = hass.states.get(ent)
            if st is None:
                return None
            return st.attributes.get(attr)

        # ---- New per-device snapshot helpers ------------------------------
        # `_resolve(new_key)` returns the entity for the new CONF model,
        # falling back to the legacy key for unmigrated config entries.
        def _resolve(new_key: str) -> Optional[str]:
            return self._entity_with_fallback(new_key)

        def _state_of(eid: Optional[str]) -> Optional[str]:
            if not eid:
                return None
            st = hass.states.get(eid)
            if st is None or st.state in ("unavailable", "unknown"):
                return None
            return st.state

        def _attr_of(eid: Optional[str], attr: str) -> Optional[Any]:
            if not eid:
                return None
            st = hass.states.get(eid)
            if st is None:
                return None
            return st.attributes.get(attr)

        def _float_state(eid: Optional[str]) -> Optional[float]:
            v = _state_of(eid)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        diag: dict[str, dict] = {}

        def _record(device: str, **kw) -> None:
            diag.setdefault(device, {}).update({k: v for k, v in kw.items() if v is not None})

        # ---- TV -----------------------------------------------------------
        tv_player = _resolve(CONF_TV_PLAYER)
        tv_active_e = _resolve(CONF_TV_ACTIVE_NEW)
        tv_power_e = _resolve(CONF_TV_POWER)
        tv_player_state = _state_of(tv_player)
        tv_source_attr = _attr_of(tv_player, "source")
        tv_active_bool = _bool_state(_state_of(tv_active_e))
        tv_power_w = _float_state(tv_power_e)
        # Fallbacks to the legacy explicit-source slot, kept for entries
        # that aren't migrated to the player-driven model yet.
        if tv_source_attr is None:
            tv_source_attr = self._entity(CONF_TV_SOURCE) and _state_of(self._entity(CONF_TV_SOURCE))
        s.tv_active = tv_active_bool or (tv_player_state in ("on", "playing", "paused"))
        s.tv_source = tv_source_attr
        s.tv_player_state = tv_player_state
        s.tv_power_w = tv_power_w
        legacy_tv_power_raw = _state(CONF_TV_POWER_FALLBACK)
        s.tv_power = (
            _bool_state(legacy_tv_power_raw) if legacy_tv_power_raw is not None
            else (tv_power_w is not None and tv_power_w > 0)
        )
        _record("tv",
                player_state=tv_player_state, active_state=tv_active_bool,
                power_w=tv_power_w, source=tv_source_attr)

        # ---- Apple TV -----------------------------------------------------
        atv = _resolve(CONF_APPLETV_PLAYER)
        s.atv_state = _state_of(atv)
        s.atv_app_id = _attr_of(atv, "app_id") or _attr_of(atv, "app_name")
        s.atv_title = _attr_of(atv, "media_title")
        _record("appletv",
                player_state=s.atv_state, app_name=_attr_of(atv, "app_name"),
                media_title=s.atv_title,
                content_type=_attr_of(atv, "media_content_type"))

        # ---- PS5 ----------------------------------------------------------
        ps5_player = _resolve(CONF_PS5_PLAYER)
        ps5_active_e = _resolve(CONF_PS5_ACTIVE)
        ps5_power_e = _resolve(CONF_PS5_POWER)
        ps5_title_e = _resolve(CONF_PS5_TITLE_ENTITY)
        ps5_network_e = _resolve(CONF_PS5_NETWORK)
        ps5_player_state = _state_of(ps5_player)
        ps5_active_bool = _bool_state(_state_of(ps5_active_e))
        ps5_power_w = _float_state(ps5_power_e)
        ps5_title_from_player = _attr_of(ps5_player, "media_title")
        ps5_title_from_entity = _state_of(ps5_title_e)
        ps5_title = ps5_title_from_player or ps5_title_from_entity
        # ps5_status keeps the legacy semantic: "on"/"playing" gate the
        # gaming branch. Prefer the active binary; fall back to player.
        if ps5_active_bool:
            s.ps5_status = "on"
        elif ps5_player_state in ("on", "playing", "paused"):
            s.ps5_status = ps5_player_state
        else:
            s.ps5_status = ps5_player_state  # may be None / "off" / "standby"
        s.ps5_title = ps5_title
        if s.ps5_status in ("on", "playing") and not s.ps5_title:
            s.ps5_title = ""  # explicit empty = menu/default
        s.ps5_player_state = ps5_player_state
        s.ps5_power_w = ps5_power_w
        s.ps5_network_state = _state_of(ps5_network_e)
        _record("ps5",
                player_state=ps5_player_state, active_state=ps5_active_bool,
                power_w=ps5_power_w, media_title=ps5_title,
                network_state=s.ps5_network_state)

        # ---- Switch -------------------------------------------------------
        sw_active_e = _resolve(CONF_SWITCH_ACTIVE)
        sw_power_e = _resolve(CONF_SWITCH_POWER)
        sw_ping_e = _resolve(CONF_SWITCH_PING)
        sw_active_bool = _bool_state(_state_of(sw_active_e))
        sw_power_w = _float_state(sw_power_e)
        sw_ping_raw = _state_of(sw_ping_e)
        sw_ping_bool: Optional[bool] = (
            _bool_state(sw_ping_raw) if sw_ping_raw is not None else None
        )
        s.switch_dock = sw_active_bool
        s.switch_power_w = sw_power_w
        s.switch_ping_on = sw_ping_bool
        # Handheld candidate: ping reachable, but the dock plug is NOT
        # drawing. Diagnostic-only — we don't promote it to a dominant
        # context per the constraint.
        s.switch_handheld_candidate = bool(
            sw_ping_bool and not sw_active_bool and (sw_power_w is None or sw_power_w < 1.0)
        )
        _record("switch",
                active_state=sw_active_bool, power_w=sw_power_w,
                network_state=sw_ping_raw,
                reasons=(["handheld_candidate"] if s.switch_handheld_candidate else None))

        # ---- PC -----------------------------------------------------------
        pc_active_e = _resolve(CONF_PC_ACTIVE_NEW)
        pc_power_e = _resolve(CONF_PC_POWER)
        s.pc_active = _bool_state(_state_of(pc_active_e))
        s.pc_power_w = _float_state(pc_power_e)
        _record("pc",
                active_state=s.pc_active, power_w=s.pc_power_w)

        # ---- Denon --------------------------------------------------------
        # Denon resolution: the new `denon_player_entity` is the
        # authoritative source-attribute provider. We only fall back
        # to reading a `source` attribute off the legacy active
        # entity when no player entity is configured — otherwise a
        # power-sensor wired into the legacy slot would shadow the
        # real media_player source. The active binary still feeds
        # `denon_active` regardless, since it's the canonical
        # plug-power "AVR is on" signal.
        # Resolve the player WITHOUT the legacy fallback: legacy
        # entries that only configured the active binary must keep
        # going through the active-binary path, never through the
        # media_player attribute read.
        denon_player = self._entity(CONF_DENON_PLAYER)
        denon_active_e = _resolve(CONF_DENON_ACTIVE_NEW)
        denon_power_e = _resolve(CONF_DENON_POWER)
        denon_player_state = _state_of(denon_player)
        denon_active_bool = _bool_state(_state_of(denon_active_e))
        denon_power_w = _float_state(denon_power_e)
        # Denon active = explicit binary OR the player itself says it's on.
        s.denon_active = denon_active_bool or (
            denon_player_state in ("on", "playing", "paused")
        )
        # Source: prefer the media_player's `source` attribute. Only
        # if no player is configured do we look at the legacy active
        # slot's attributes (some users wire a media_player into the
        # legacy denon_active key).
        if denon_player:
            s.denon_source = _attr_of(denon_player, "source")
        else:
            s.denon_source = _attr_of(denon_active_e, "source")
        s.denon_player_state = denon_player_state
        s.denon_power_w = denon_power_w
        _record("denon",
                player_state=denon_player_state, active_state=denon_active_bool,
                power_w=denon_power_w, source=s.denon_source)

        # ---- HomePods -----------------------------------------------------
        # New model: a single media_player entity (often a group). Keep
        # backwards compat with the legacy multi-entity list.
        hp_playing = False
        hp_volume: Optional[float] = None
        hp_player_state: Optional[str] = None
        homepods_single = self._entity(CONF_HOMEPODS_PLAYER)
        if homepods_single:
            st = hass.states.get(homepods_single)
            if st is not None:
                hp_player_state = st.state
                if st.state == "playing":
                    hp_playing = True
                try:
                    hp_volume = float(st.attributes.get("volume_level"))
                except (TypeError, ValueError):
                    hp_volume = None
        else:
            for ent in self._entities_list(CONF_HOMEPODS):
                st = hass.states.get(ent)
                if st and st.state == "playing":
                    hp_playing = True
                    hp_player_state = st.state
                    break
        s.homepods_playing = hp_playing
        s.homepods_volume_level = hp_volume
        s.homepods_state = hp_player_state
        _record("homepods",
                player_state=hp_player_state, volume_level=hp_volume)
        # ---- Per-device configuration/resolution diagnostics ------------
        # For every device card, stamp the configured CONF_* values plus
        # which key (new vs legacy) actually resolved. This is what the
        # entity attribute view surfaces so users can see at a glance
        # whether the runtime is reading from the new model or still
        # falling back to a legacy slot.
        _ROLE_SUFFIX = {
            "_player_entity": "player",
            "_active_entity": "active",
            "_power_entity": "power",
            "_title_entity": "title",
            "_ping_entity": "ping",
            "_network_entity": "network",
        }

        def _role_for(key: str) -> Optional[str]:
            for suffix, role in _ROLE_SUFFIX.items():
                if key.endswith(suffix):
                    return role
            return None

        for card, keys in DEVICE_CARDS.items():
            bucket = diag.setdefault(card, {})
            sources: dict[str, str] = {}
            for key in keys:
                role = _role_for(key)
                if not role:
                    continue
                eid, origin = self._resolve_with_origin(key)
                bucket[f"configured_{role}_entity"] = eid
                if origin:
                    sources[role] = origin
            if "player" in sources:
                bucket["player_source"] = bucket.get("source")  # alias for clarity
            # Single rolled-up "resolution_source": "new_key" if every
            # configured slot resolved via the new key, "legacy_fallback"
            # if any slot fell back, None if nothing is configured.
            origins = set(sources.values())
            if not origins:
                bucket["resolution_source"] = None
            elif origins == {"new_key"}:
                bucket["resolution_source"] = "new_key"
            else:
                bucket["resolution_source"] = "legacy_fallback"
            bucket["resolution_per_role"] = sources

        s.device_diagnostics = diag

        s.classifier_ps5 = _maybe_int(_state(CONF_TITLE_CLASSIFIER_PS5))
        s.classifier_pc = _maybe_int(_state(CONF_TITLE_CLASSIFIER_PC))
        s.classifier_homepods = _maybe_int(_state(CONF_TITLE_CLASSIFIER_HOMEPODS))
        s.classifier_media = _maybe_int(_state(CONF_TITLE_CLASSIFIER_MEDIA))

        s.door_open = _bool_state(_state(CONF_DOOR))
        s.call_active = _bool_state(_state(CONF_CALL_MONITOR))
        s.day_state = _state(CONF_DAY_STATE)
        s.activity_state = _state(CONF_ACTIVITY_STATE)
        s.window_open = _bool_state(_state(CONF_WINDOW_STATE))

        s.manual_nudge = self._manual_nudge

        # ---- Orchestrator inputs ----------------------------------------
        bio_raw = _state(CONF_BIO_STATE)
        s.bio_state = bio_raw
        s.bio_sleep = (
            bio_raw is not None and str(bio_raw).lower() in BIO_SLEEP_VALUES
        )
        s.manual_playback_active = _bool_state(_state(CONF_MANUAL_PLAYBACK))
        s.planned_radio_active = _bool_state(_state(CONF_PLANNED_RADIO))

        # New 0.3.8 orchestrator-input slots. Tri-state semantics:
        # `None` means "not configured" — orchestrators fall back to
        # legacy heuristics. `True` / `False` come straight from the
        # configured binary sensor.
        def _opt_bool(key: str) -> Optional[bool]:
            if not self._entity(key):
                return None
            raw = _state(key)
            if raw is None:
                return None
            return _bool_state(raw)

        s.pc_gaming_active = _opt_bool(CONF_PC_GAMING_ACTIVE)
        s.media_stop_latch = _opt_bool(CONF_MEDIA_STOP_LATCH)
        s.opening_any_open = _opt_bool(CONF_OPENING_ANY_OPEN)
        s.quiet_mode_external = _opt_bool(CONF_QUIET_MODE_ENTITY)

        return s

    # -- input-resolution helpers --
    def _resolve_orchestrator_inputs(
        self,
    ) -> tuple[dict[str, Optional[str]], list[str], list[str]]:
        """Resolve every orchestrator input declared in ``ORCH_INPUTS``.

        Returns:
            ``(configured_entities, missing_orchestrator_inputs,
            missing_volume_inputs)``.

        Resolution honours the existing legacy fallbacks (so an entry
        that hasn't been migrated to the new CONF model still wires
        the orchestrator inputs correctly via ``LEGACY_FALLBACKS``
        / the registry's third tuple element). ``missing_*_inputs``
        only lists the names that the respective orchestrator
        actually needs in order to act — purely "nice to have"
        inputs don't pollute the debug list.
        """
        resolved: dict[str, Optional[str]] = {}
        for name, primary, legacy in ORCH_INPUTS:
            eid = self._entity(primary)
            if not eid and legacy:
                eid = self._entity(legacy)
            resolved[name] = eid

        missing_audio = [
            n for n in ORCH_REQUIRED_INPUTS if not resolved.get(n)
        ]
        # Volume orchestrator can run on either speaker, but blocked
        # when both are missing — that's the contract surfaced via
        # ``missing_volume_inputs``.
        vol_missing = [n for n in VOL_PRIMARY_INPUTS if not resolved.get(n)]
        # If at least one is configured, treat the other as "fine to
        # be missing" — the volume orchestrator just routes audio to
        # whichever exists. Only flag both-missing as a real gap.
        if len(vol_missing) < len(VOL_PRIMARY_INPUTS):
            vol_missing = []
        return resolved, missing_audio, vol_missing

    def _volume_settings(self) -> VolumeSettings:
        """Hydrate the VolumeSettings dataclass from options/data."""
        def _f(key: str, default: float) -> float:
            try:
                return float(self._opt(key, default))
            except (TypeError, ValueError):
                return default

        return VolumeSettings(
            homepods_base=_f(CONF_VOL_HOMEPODS_BASE, DEFAULT_VOL_HOMEPODS_BASE),
            denon_base=_f(CONF_VOL_DENON_BASE, DEFAULT_VOL_DENON_BASE),
            ducked_target=_f(CONF_VOL_DUCKED_TARGET, DEFAULT_VOL_DUCKED_TARGET),
            homepods_max=_f(CONF_VOL_HOMEPODS_MAX, DEFAULT_VOL_HOMEPODS_MAX),
            denon_max=_f(CONF_VOL_DENON_MAX, DEFAULT_VOL_DENON_MAX),
            active_min=_f(CONF_VOL_ACTIVE_MIN, DEFAULT_VOL_ACTIVE_MIN),
            night_offset=_f(CONF_VOL_NIGHT_OFFSET, DEFAULT_VOL_NIGHT_OFFSET),
            edge_day_offset=_f(CONF_VOL_EDGE_DAY_OFFSET, DEFAULT_VOL_EDGE_DAY_OFFSET),
            opening_offset=_f(CONF_VOL_OPENING_OFFSET, DEFAULT_VOL_OPENING_OFFSET),
        )

    # -- recalculate --
    async def async_recalculate(self) -> None:
        snap = self._build_snapshot()
        new = decide(
            snap,
            app_map=self._app_map(),
            base_homepods=float(self._opt(CONF_BASE_VOL_HOMEPODS, DEFAULT_BASE_VOL_HOMEPODS)),
            base_denon=float(self._opt(CONF_BASE_VOL_DENON, DEFAULT_BASE_VOL_DENON)),
            boost_offset=float(self._opt(CONF_BOOST_OFFSET, DEFAULT_BOOST_OFFSET)),
            window_offset=float(self._opt(CONF_WINDOW_OFFSET, DEFAULT_WINDOW_OFFSET)),
            quiet_duck=float(self._opt(CONF_QUIET_DUCK, DEFAULT_QUIET_DUCK)),
            pre_atv_scenario=self._pre_atv_scenario,
        )
        debounce = float(self._opt(CONF_DEBOUNCE, DEFAULT_DEBOUNCE))
        now = time.monotonic()

        # Quiet bypasses debounce
        if new.quiet_mode_active or self.data.quiet_mode_active:
            self._commit(new, snap)
            return

        # Same context as last stable -> commit immediately (refresh attrs)
        if (
            new.context == self._last_stable.context
            and new.subcontext == self._last_stable.subcontext
        ):
            self._pending_decision = None
            self._commit(new, snap)
            return

        # Different context -> debounce
        if self._pending_decision is None or (
            new.context != self._pending_decision.context
            or new.subcontext != self._pending_decision.subcontext
        ):
            self._pending_decision = new
            self._pending_since = now
            interim = Decision(**self._last_stable.to_dict())
            interim.volume_target_homepods = new.volume_target_homepods
            interim.volume_target_denon = new.volume_target_denon
            interim.subwoofer_allowed = new.subwoofer_allowed
            interim.active_reasons = self._last_stable.active_reasons + [
                f"debouncing->{new.context}/{new.subcontext}"
            ]
            # During debounce we still want the freshest per-device
            # diagnostics surfaced — the entity attributes shouldn't go
            # stale just because the context is in transition.
            interim.device_diagnostics = dict(new.device_diagnostics or {})
            # Keep the last stable orchestrator output visible during
            # debounce so the audio_owner / homepods_action sensors
            # don't flap.
            interim.orchestrator = self._last_stable.orchestrator
            interim.volume = self._last_stable.volume
            self.async_set_updated_data(interim)
            self.hass.loop.call_later(
                debounce + 0.1,
                lambda: self.hass.async_create_task(self.async_recalculate()),
            )
            return

        if now - self._pending_since >= debounce:
            self._commit(new, snap)
        else:
            interim = Decision(**self._last_stable.to_dict())
            interim.active_reasons = self._last_stable.active_reasons + [
                f"debouncing->{new.context}/{new.subcontext}"
            ]
            interim.device_diagnostics = dict(new.device_diagnostics or {})
            interim.orchestrator = self._last_stable.orchestrator
            interim.volume = self._last_stable.volume
            self.async_set_updated_data(interim)

    def _commit(self, new: Decision, snap: Snapshot) -> None:
        if self._last_stable.context not in (CTX_STREAMING,) and new.context == CTX_STREAMING:
            # entering streaming -> remember what we had before
            self._pre_atv_scenario = self._last_stable

        # Compute the audio orchestrator decision against the freshly
        # committed snap and the persistent orchestrator state. Only
        # update _orch_state at commit time so debounce-driven
        # recomputes don't double-consume transitions.
        configured_entities, missing_audio, missing_vol = (
            self._resolve_orchestrator_inputs()
        )
        od, new_orch_state = decide_audio_orchestrator(
            snap,
            new,
            bio_sleep=snap.bio_sleep,
            manual_playback_active=snap.manual_playback_active,
            planned_radio_active=snap.planned_radio_active,
            homepods_state=snap.homepods_state,
            state=self._orch_state,
            configured_entities=configured_entities,
            missing_orchestrator_inputs=missing_audio,
            missing_volume_inputs=missing_vol,
        )
        self._orch_state = new_orch_state
        new.orchestrator = od

        # Volume orchestrator runs off the audio decision + raw
        # snapshot signals. It doesn't carry state across ticks (yet).
        vol = decide_volume(
            audio_owner=od.audio_owner,
            bio_sleep=snap.bio_sleep,
            quiet_mode_active=new.quiet_mode_active,
            bio_state=snap.bio_state,
            day_state=snap.day_state,
            opening_any_open=bool(snap.opening_any_open),
            homepods_configured=bool(configured_entities.get("homepods_player_entity")),
            denon_configured=bool(configured_entities.get("denon_player_entity")),
            settings=self._volume_settings(),
        )
        new.volume = vol

        self._last_stable = new
        self._pending_decision = None
        # Stash the snapshot so entity attributes (denon_active /
        # denon_source on subwoofer_allowed) can surface raw inputs
        # without having to re-read hass.states.
        self._last_snapshot = snap
        self.async_set_updated_data(new)

    # -- service hooks --
    def set_manual_nudge(self, value: str) -> None:
        self._manual_nudge = value
        self.hass.async_create_task(self.async_recalculate())

    def clear_manual_nudge(self) -> None:
        self._manual_nudge = None
        self.hass.async_create_task(self.async_recalculate())


# ------------------------------------------------------------------ lookups


def coordinator_from_hass(hass: HomeAssistant, entry_id: str) -> BenniMediaCoordinator | None:
    bucket = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry_id)
    if not bucket:
        return None
    return bucket.get("coordinator")


def all_benni_media_context_coordinators(hass: HomeAssistant) -> list[BenniMediaCoordinator]:
    out: list[BenniMediaCoordinator] = []
    for bucket in hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).values():
        if bucket.get("module_id") != MODULE_ID:
            continue
        c = bucket.get("coordinator")
        if c is not None:
            out.append(c)
    return out
