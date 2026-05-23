"""Subwoofer policy for benni_media_context.

The subwoofer lives downstream of the Denon AVR. When the audio path is
running through the Denon (PC gaming via TV Audio, Denon-driven
streaming, …) the sub should be available even if a window is open.
Explicit blockers still win: quiet mode, no entertainment, headset, and
window-open WITHOUT a Denon path.
"""
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


# ---------------------------------------------------------------------------
# 1) PC gaming via Denon: subwoofer must be allowed.
# ---------------------------------------------------------------------------


def test_pc_gaming_denon_off_subwoofer_blocked():
    """PC gaming but Denon path is dead → sub has no route, stay off."""
    d = L.decide(_snap(pc_active=True, denon_active=False), **DEFAULT_OPTS)
    assert d.context == C.CTX_GAMING
    assert d.device == C.DEV_PC
    assert d.entertainment_active is True
    assert d.denon_audio_path is False
    # Window closed AND no denon path → policy allows (window is the
    # only reason we'd refuse without denon).
    assert d.subwoofer_allowed is True
    assert d.subwoofer_block_reason is None


def test_pc_gaming_denon_on_subwoofer_allowed():
    """The Einhornzentrale lab case: PC gaming, Denon routes TV Audio.
    Sub should be allowed and `denon_audio_path` reported as True."""
    d = L.decide(
        _snap(pc_active=True, denon_active=True, denon_source="TV Audio"),
        **DEFAULT_OPTS,
    )
    assert d.context == C.CTX_GAMING
    assert d.device == C.DEV_PC
    assert d.denon_audio_path is True
    assert d.subwoofer_allowed is True
    assert d.subwoofer_block_reason is None


def test_pc_gaming_denon_source_alone_marks_denon_audio_path():
    """If the Denon media_player exposes a non-empty `source` attr but
    the boolean `denon_active` signal isn't wired up, we still treat
    that as the audio path being active."""
    d = L.decide(
        _snap(pc_active=True, denon_active=False, denon_source="TV Audio"),
        **DEFAULT_OPTS,
    )
    assert d.denon_audio_path is True
    assert d.subwoofer_allowed is True


def test_denon_source_off_does_not_count_as_audio_path():
    d = L.decide(
        _snap(pc_active=True, denon_active=False, denon_source="off"),
        **DEFAULT_OPTS,
    )
    assert d.denon_audio_path is False


# ---------------------------------------------------------------------------
# 2) Window open: denon path keeps sub on, no path turns it off.
# ---------------------------------------------------------------------------


def test_window_open_with_denon_keeps_subwoofer_on():
    d = L.decide(
        _snap(pc_active=True, denon_active=True, window_open=True),
        **DEFAULT_OPTS,
    )
    assert d.denon_audio_path is True
    assert d.subwoofer_allowed is True
    assert d.subwoofer_block_reason is None


def test_window_open_without_denon_blocks_subwoofer():
    d = L.decide(
        _snap(pc_active=True, denon_active=False, window_open=True),
        **DEFAULT_OPTS,
    )
    assert d.denon_audio_path is False
    assert d.subwoofer_allowed is False
    assert d.subwoofer_block_reason == "window_open_no_denon_path"


# ---------------------------------------------------------------------------
# 3) Quiet / headset / no entertainment block regardless of denon path.
# ---------------------------------------------------------------------------


def test_quiet_mode_blocks_subwoofer_even_with_denon():
    d = L.decide(
        _snap(pc_active=True, denon_active=True, call_active=True),
        **DEFAULT_OPTS,
    )
    assert d.quiet_mode_active is True
    assert d.subwoofer_allowed is False
    assert d.subwoofer_block_reason == "quiet_mode"
    # Diagnostic field still populated for the entity attribute.
    assert d.denon_audio_path is True


def test_headset_active_blocks_subwoofer():
    """PC gaming with classifier flagging headset → sub must stay off.
    Speakers + headset is the wrong combo for a subwoofer."""
    d = L.decide(
        _snap(pc_active=True, denon_active=True,
              classifier_pc=C.CLASSIFIER_GAME_HEADSET),
        **DEFAULT_OPTS,
    )
    assert d.headset_active is True
    assert d.denon_audio_path is True
    assert d.subwoofer_allowed is False
    assert d.subwoofer_block_reason == "headset_active"


def test_idle_blocks_subwoofer_with_no_entertainment_reason():
    """No device at all → no entertainment → sub blocked with the
    explicit "no_entertainment" reason."""
    d = L.decide(_snap(), **DEFAULT_OPTS)
    assert d.entertainment_active is False
    assert d.subwoofer_allowed is False
    assert d.subwoofer_block_reason == "no_entertainment"


# ---------------------------------------------------------------------------
# 4) gaming_grind keeps sub on (no regression — existing behaviour).
# ---------------------------------------------------------------------------


def test_gaming_grind_still_allows_subwoofer():
    """gaming_grind is a quieter sub-context but currently does not
    explicitly block the subwoofer. Pin this so a future blocker can
    only be added on purpose."""
    d = L.decide(
        _snap(pc_active=True, denon_active=True,
              classifier_pc=C.CLASSIFIER_GAME_GRIND),
        **DEFAULT_OPTS,
    )
    assert d.subcontext == C.SUB_GAME_GRIND
    assert d.headset_active is False
    assert d.subwoofer_allowed is True
    assert d.subwoofer_block_reason is None


# ---------------------------------------------------------------------------
# 5) Denon-only audio (streaming via AVR) keeps sub on.
# ---------------------------------------------------------------------------


def test_denon_audio_only_streaming_allows_subwoofer():
    """No TV, no gaming — just music streaming through Denon. Should
    still drop into streaming_default with the sub allowed."""
    d = L.decide(_snap(denon_active=True, denon_source="Spotify"), **DEFAULT_OPTS)
    assert d.context == C.CTX_STREAMING
    assert d.entertainment_active is True
    assert d.denon_audio_path is True
    assert d.subwoofer_allowed is True
