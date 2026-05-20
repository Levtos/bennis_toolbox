"""Tests for pure decision logic."""
import bmc_logic as L
import bmc_const as C

DEFAULT_OPTS = dict(
    app_map=C.DEFAULT_APPLETV_APP_MAP,
    base_homepods=0.35,
    base_denon=0.40,
    boost_offset=0.10,
    window_offset=-0.05,
    quiet_duck=0.15,
)


def _snap(**kw):
    s = L.Snapshot()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_idle_default():
    d = L.decide(_snap(), **DEFAULT_OPTS)
    assert d.context == C.CTX_IDLE
    assert d.subcontext == C.SUB_NONE
    assert d.entertainment_active is False


def test_tv_alone():
    d = L.decide(_snap(tv_active=True), **DEFAULT_OPTS)
    assert d.context == C.CTX_TV
    assert d.subcontext == C.SUB_TV_DEFAULT
    assert d.device == C.DEV_TV


def test_tv_source_ard():
    d = L.decide(_snap(tv_active=True, tv_source="ARD"), **DEFAULT_OPTS)
    assert d.subcontext == C.SUB_TV_ARD


def test_appletv_netflix():
    d = L.decide(
        _snap(atv_state="playing", atv_app_id="com.netflix.Netflix"),
        **DEFAULT_OPTS,
    )
    assert d.context == C.CTX_STREAMING
    assert d.subcontext == C.SUB_STR_NETFLIX
    assert d.device == C.DEV_APPLETV


def test_appletv_unknown_app_defaults():
    d = L.decide(
        _snap(atv_state="playing", atv_app_id="com.example.foo"),
        **DEFAULT_OPTS,
    )
    assert d.subcontext == C.SUB_STR_DEFAULT


def test_appletv_system_app_rollback_to_tv():
    pre = L.Decision(context=C.CTX_TV, subcontext=C.SUB_TV_ARD)
    d = L.decide(
        _snap(atv_state="playing", atv_app_id="com.apple.TVSettings",
              tv_active=True, tv_source="ARD"),
        pre_atv_scenario=pre,
        **DEFAULT_OPTS,
    )
    # ATV system app rollback wins via pre_atv_scenario
    assert d.context == C.CTX_TV
    assert d.subcontext == C.SUB_TV_ARD


def test_ps5_grind():
    d = L.decide(
        _snap(ps5_status="playing", ps5_title="Helldivers", classifier_ps5=1),
        **DEFAULT_OPTS,
    )
    assert d.context == C.CTX_GAMING
    assert d.subcontext == C.SUB_GAME_GRIND
    assert d.gaming_platform == C.GP_PS5
    assert d.gaming_source == C.GS_TV
    assert d.headset_active is False


def test_pc_headset():
    d = L.decide(
        _snap(pc_active=True, classifier_pc=2),
        **DEFAULT_OPTS,
    )
    assert d.context == C.CTX_GAMING
    assert d.subcontext == C.SUB_GAME_HEADSET
    assert d.gaming_platform == C.GP_PC
    assert d.gaming_source == C.GS_PC
    assert d.headset_active is True


def test_switch_default_regardless_of_enum():
    d = L.decide(
        _snap(switch_dock=True, classifier_ps5=2),  # PS5 enum irrelevant
        **DEFAULT_OPTS,
    )
    assert d.context == C.CTX_GAMING
    assert d.subcontext == C.SUB_GAME_DEFAULT
    assert d.gaming_platform == C.GP_SWITCH


def test_ps5_empty_title_is_default_not_unknown():
    d = L.decide(
        _snap(ps5_status="on", ps5_title="", classifier_ps5=0),
        **DEFAULT_OPTS,
    )
    assert d.context == C.CTX_GAMING
    assert d.subcontext == C.SUB_GAME_DEFAULT


def test_quiet_mode_door():
    d = L.decide(_snap(tv_active=True, door_open=True), **DEFAULT_OPTS)
    assert d.quiet_mode_active is True
    assert d.context == C.CTX_PRIVATE
    assert d.entertainment_active is False
    assert d.volume_target_homepods <= 0.15


def test_quiet_mode_call():
    d = L.decide(_snap(atv_state="playing", atv_app_id="com.netflix.Netflix", call_active=True), **DEFAULT_OPTS)
    assert d.quiet_mode_active is True
    assert d.quiet_mode_reason == "call_active"


def test_classifier_media_mute_triggers_quiet():
    d = L.decide(_snap(tv_active=True, classifier_media=2), **DEFAULT_OPTS)
    assert d.quiet_mode_active is True


def test_classifier_media_boost_raises_volume():
    d = L.decide(_snap(tv_active=True, classifier_media=1), **DEFAULT_OPTS)
    assert d.volume_target_homepods == 0.35 + 0.10


def test_window_open_lowers_and_blocks_sub():
    d = L.decide(_snap(tv_active=True, window_open=True), **DEFAULT_OPTS)
    assert d.volume_target_homepods == 0.35 - 0.05
    assert d.subwoofer_allowed is False


def test_classifier_enum_zero_is_default():
    d = L.decide(_snap(pc_active=True, classifier_pc=0), **DEFAULT_OPTS)
    assert d.subcontext == C.SUB_GAME_DEFAULT


def test_unavailable_sources_fail_safe_to_idle():
    # No sources -> idle, no crash
    d = L.decide(_snap(), **DEFAULT_OPTS)
    assert d.context == C.CTX_IDLE


def test_gaming_beats_streaming_when_both_active():
    d = L.decide(
        _snap(ps5_status="playing", classifier_ps5=1, atv_state="playing", atv_app_id="com.netflix.Netflix"),
        **DEFAULT_OPTS,
    )
    assert d.context == C.CTX_GAMING


def test_manual_nudge_overrides():
    d = L.decide(_snap(manual_nudge=C.SUB_STR_DISNEY), **DEFAULT_OPTS)
    assert d.context == C.CTX_STREAMING
    assert d.subcontext == C.SUB_STR_DISNEY


def test_homepods_audio_only_is_streaming_default():
    d = L.decide(_snap(homepods_playing=True), **DEFAULT_OPTS)
    assert d.context == C.CTX_STREAMING
    assert d.subcontext == C.SUB_STR_DEFAULT
