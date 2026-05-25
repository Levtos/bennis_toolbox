"""Sensor + Binary-Sensor-Entities für Benni Media Context."""

from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import DOMAIN, unique_id
from .const import (
    ACTION_NONE,
    AUDIO_OWNER_NONE,
    MODULE_ID,
)
from .coordinator import BenniMediaCoordinator, coordinator_from_hass
from .orchestrator import OrchestratorDecision


def _device_info(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{MODULE_ID}_{entry.entry_id}")},
        "name": "Benni Media Context",
        "manufacturer": "Benni's Toolbox",
        "model": "Media Context",
    }


async def async_get_entities(
    hass: HomeAssistant, entry: ConfigEntry, platform: Platform
) -> list:
    coord = coordinator_from_hass(hass, entry.entry_id)
    if coord is None:
        return []
    if platform == Platform.SENSOR:
        return [
            _ContextSensor(coord, entry),
            _SubcontextSensor(coord, entry),
            _DeviceSensor(coord, entry),
            _GamingSourceSensor(coord, entry),
            _GamingPlatformSensor(coord, entry),
            _VolHomePodsSensor(coord, entry),
            _VolDenonSensor(coord, entry),
            _HomePodsActionSensor(coord, entry),
            _AudioOwnerSensor(coord, entry),
        ]
    if platform == Platform.BINARY_SENSOR:
        return [
            _HeadsetActive(coord, entry),
            _EntertainmentActive(coord, entry),
            _QuietModeActive(coord, entry),
            _SubwooferAllowed(coord, entry),
            _HomePodsShouldPause(coord, entry),
            _HomePodsResumeAllowed(coord, entry),
        ]
    return []


# --------------------------------------------------------------------- sensor


class _BaseSensor(CoordinatorEntity[BenniMediaCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _key: str = ""

    def __init__(self, coord: BenniMediaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coord)
        self._entry = entry
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, self._key)
        self._attr_device_info = _device_info(entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        return {
            "subcontext": d.subcontext,
            "device": d.device,
            "gaming_source": d.gaming_source,
            "gaming_platform": d.gaming_platform,
            "headset_active": d.headset_active,
            "entertainment_active": d.entertainment_active,
            "quiet_mode_active": d.quiet_mode_active,
            "quiet_mode_reason": d.quiet_mode_reason,
            "active_reasons": d.active_reasons,
            "volume_target_homepods": d.volume_target_homepods,
            "volume_target_denon": d.volume_target_denon,
            "subwoofer_allowed": d.subwoofer_allowed,
        }


class _ContextSensor(_BaseSensor):
    _key = "media_context"
    _attr_name = "Media Context"
    _attr_translation_key = "media_context"

    @property
    def native_value(self):
        return self.coordinator.data.context

    @property
    def extra_state_attributes(self):
        # The two top-of-the-list sensors are the natural place for the
        # per-device diagnostics dict — surface it so users (and Lovelace)
        # can see configured_player_entity / resolution_source / etc.
        attrs = super().extra_state_attributes
        attrs["device_diagnostics"] = getattr(
            self.coordinator.data, "device_diagnostics", {}
        )
        return attrs


class _SubcontextSensor(_BaseSensor):
    _key = "media_subcontext"
    _attr_name = "Media Subcontext"
    _attr_translation_key = "media_subcontext"

    @property
    def native_value(self):
        return self.coordinator.data.subcontext


class _DeviceSensor(_BaseSensor):
    _key = "media_device"
    _attr_name = "Media Device"

    @property
    def native_value(self):
        return self.coordinator.data.device

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        attrs["device_diagnostics"] = getattr(
            self.coordinator.data, "device_diagnostics", {}
        )
        return attrs


class _GamingSourceSensor(_BaseSensor):
    _key = "gaming_source"
    _attr_name = "Gaming Source"

    @property
    def native_value(self):
        return self.coordinator.data.gaming_source


class _GamingPlatformSensor(_BaseSensor):
    _key = "gaming_platform"
    _attr_name = "Gaming Platform"

    @property
    def native_value(self):
        return self.coordinator.data.gaming_platform


class _VolHomePodsSensor(_BaseSensor):
    _key = "volume_target_homepods"
    _attr_name = "Media Volume Target HomePods"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return round(self.coordinator.data.volume_target_homepods, 3)


class _VolDenonSensor(_BaseSensor):
    _key = "volume_target_denon"
    _attr_name = "Media Volume Target Denon"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return round(self.coordinator.data.volume_target_denon, 3)


# -------------------------------------------------------------- binary_sensor


class _BaseBinary(CoordinatorEntity[BenniMediaCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _key: str = ""

    def __init__(self, coord: BenniMediaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coord)
        self._entry = entry
        self._attr_unique_id = unique_id(MODULE_ID, entry.entry_id, self._key)
        self._attr_device_info = _device_info(entry)

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        return {
            "context": d.context,
            "subcontext": d.subcontext,
            "active_reasons": d.active_reasons,
        }


class _HeadsetActive(_BaseBinary):
    _key = "headset_active"
    _attr_name = "Headset Active"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.headset_active


class _EntertainmentActive(_BaseBinary):
    _key = "entertainment_active"
    _attr_name = "Entertainment Active"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.entertainment_active


class _QuietModeActive(_BaseBinary):
    _key = "quiet_mode_active"
    _attr_name = "Quiet Mode Active"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.quiet_mode_active

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        attrs["quiet_mode_reason"] = self.coordinator.data.quiet_mode_reason
        return attrs


class _SubwooferAllowed(_BaseBinary):
    _key = "subwoofer_allowed"
    _attr_name = "Subwoofer Allowed"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.subwoofer_allowed

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        d = self.coordinator.data
        snap_src = getattr(self.coordinator, "_last_snapshot", None)
        attrs["denon_active"] = bool(snap_src.denon_active) if snap_src else None
        attrs["denon_source"] = snap_src.denon_source if snap_src else None
        attrs["denon_audio_path"] = d.denon_audio_path
        attrs["subwoofer_block_reason"] = d.subwoofer_block_reason
        return attrs


# --------------------------------------------------- audio orchestrator
#
# All four entities below read from the same `OrchestratorDecision` payload
# attached to `coordinator.data.orchestrator`. The attribute set is
# identical across the four entities so the HA Devtools Template view can
# inspect every signal — winning stack, blockers, per-device states — from
# whichever entity the user happens to look at first.


def _orchestrator_attrs(od: Optional[OrchestratorDecision]) -> dict[str, Any]:
    """Build the full attribute set for the orchestrator entities."""
    if od is None:
        # Pre-first-commit state: surface stable defaults so HA template
        # automations don't see `None` flicker on startup.
        od = OrchestratorDecision()
    return {
        "reason": od.reason,
        "blocked_reason": od.blocked_reason,
        "media_context": od.media_context,
        "media_subcontext": od.media_subcontext,
        "media_device": od.media_device,
        "gaming_source": od.gaming_source,
        "gaming_platform": od.gaming_platform,
        "entertainment_active": od.entertainment_active,
        "tv_state": od.tv_state,
        "appletv_state": od.appletv_state,
        "ps5_state": od.ps5_state,
        "switch_state": od.switch_state,
        "pc_gaming_active": od.pc_gaming_active,
        "denon_state": od.denon_state,
        "denon_audio_path": od.denon_audio_path,
        "homepods_state": od.homepods_state,
        "manual_playback_active": od.manual_playback_active,
        "planned_radio_active": od.planned_radio_active,
        "bio_sleep": od.bio_sleep,
        "auto_paused_homepods": od.auto_paused_homepods,
        "resume_candidate": od.resume_candidate,
        # Detailed debug — which signals were active when the
        # orchestrator picked the winner.
        "audio_owner": od.audio_owner,
        "winning_stack": od.winning_stack,
        "private_signal_active": od.private_signal_active,
        "gaming_signal_active": od.gaming_signal_active,
        "streaming_signal_active": od.streaming_signal_active,
        "tv_signal_active": od.tv_signal_active,
        "ps5_gaming_active": od.ps5_gaming_active,
        "switch_gaming_active": od.switch_gaming_active,
        "should_pause": od.should_pause,
        "resume_allowed": od.resume_allowed,
        "action": od.action,
    }


class _HomePodsShouldPause(_BaseBinary):
    _key = "homepods_should_pause"
    _attr_name = "HomePods Should Pause"

    @property
    def is_on(self) -> bool:
        od = self.coordinator.data.orchestrator
        return bool(od and od.should_pause)

    @property
    def extra_state_attributes(self):
        return _orchestrator_attrs(self.coordinator.data.orchestrator)


class _HomePodsResumeAllowed(_BaseBinary):
    _key = "homepods_resume_allowed"
    _attr_name = "HomePods Resume Allowed"

    @property
    def is_on(self) -> bool:
        od = self.coordinator.data.orchestrator
        return bool(od and od.resume_allowed)

    @property
    def extra_state_attributes(self):
        return _orchestrator_attrs(self.coordinator.data.orchestrator)


class _HomePodsActionSensor(_BaseSensor):
    _key = "homepods_action"
    _attr_name = "HomePods Action"

    @property
    def native_value(self):
        od = self.coordinator.data.orchestrator
        return od.action if od else ACTION_NONE

    @property
    def extra_state_attributes(self):
        return _orchestrator_attrs(self.coordinator.data.orchestrator)


class _AudioOwnerSensor(_BaseSensor):
    _key = "audio_owner"
    _attr_name = "Audio Owner"

    @property
    def native_value(self):
        od = self.coordinator.data.orchestrator
        return od.audio_owner if od else AUDIO_OWNER_NONE

    @property
    def extra_state_attributes(self):
        return _orchestrator_attrs(self.coordinator.data.orchestrator)
