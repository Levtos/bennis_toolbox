"""Pure-helper tests for the Title Classifier module.

Covers key extraction, media duplicate resolution, scoring, and
user-input normalisation — everything that decides whether two
different player reports map to the same classifiable key.
"""

from __future__ import annotations

import pytest

import tc_runtime as R


# --------------------------------------------------------------- clean_value


@pytest.mark.parametrize("raw", ["", "Unknown", "unavailable", "none", "off", "idle", "standby"])
def test_clean_value_drops_idle_markers(raw):
    assert R.clean_value(raw) is None


def test_clean_value_strips_and_keeps():
    assert R.clean_value("  Stardew Valley  ") == "Stardew Valley"
    assert R.clean_value(None) is None
    assert R.clean_value(0) == "0"  # numeric coerced to str, not in IGNORED


# ---------------------------------------------------------------- split_key


def test_split_media_key_with_artist():
    assert R.split_media_key("Daft Punk - Around the World") == (
        "Daft Punk", "Around the World"
    )


def test_split_media_key_without_artist():
    assert R.split_media_key("Standalone Title") == ("", "Standalone Title")


# -------------------------------------------------------------- normalise


def test_normalise_artist_drops_features():
    assert R.normalise_artist("Daft Punk feat. Pharrell Williams") == "daft punk"
    assert R.normalise_artist("Daft Punk & Pharrell") == "daft punk"
    assert R.normalise_artist("Daft Punk, Pharrell") == "daft punk"


def test_normalise_title_drops_brackets():
    assert R.normalise_title("Get Lucky (Radio Edit)") == "get lucky"


# ----------------------------------------------------------- duplicate match


def test_media_keys_match_for_same_song_different_metadata():
    a = "Daft Punk feat. Pharrell - Get Lucky"
    b = "Daft Punk - Get Lucky (Radio Edit)"
    assert R.media_keys_match(a, b)


def test_media_keys_no_match_for_different_titles():
    assert not R.media_keys_match(
        "Daft Punk - Get Lucky",
        "Daft Punk - One More Time",
    )


def test_media_keys_no_match_for_different_artists():
    assert not R.media_keys_match(
        "Daft Punk - Get Lucky",
        "Justice - Get Lucky",
    )


# ------------------------------------------------------------------ scoring


def test_media_title_score_prefers_remix_marker():
    plain = R.media_title_score("Get Lucky")
    remix = R.media_title_score("Get Lucky (Radio Edit)")
    assert remix > plain


def test_media_key_score_prefers_feature_artist():
    plain = R.media_key_score("Daft Punk - Get Lucky")
    feat = R.media_key_score("Daft Punk feat. Pharrell - Get Lucky")
    assert feat > plain


# ----------------------------------------------------------------- normalise


def test_normalise_user_key_strips_and_validates():
    assert R.normalise_user_key("  Helldivers  ") == "Helldivers"
    # ServiceValidationError comes through our stubbed homeassistant.exceptions.
    with pytest.raises(R.ServiceValidationError):
        R.normalise_user_key("   ")
