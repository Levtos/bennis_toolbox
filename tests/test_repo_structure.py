"""Smoke-Tests für die Monorepo-Struktur.

Diese Tests prüfen *Repo-Hygiene*, nicht das HA-Verhalten:
- Jede Integration hat ein valides manifest.json mit eindeutiger Domain.
- Ordnername == Domain.
- Keine Cross-Imports zwischen Teilintegrationen.
- Dachintegration hat config_flow und kennt alle Member im Code (KNOWN_MEMBERS).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CC = REPO / "custom_components"
UMBRELLA = "bennis_toolbox"


def _integration_dirs() -> list[Path]:
    return sorted(p for p in CC.iterdir() if p.is_dir() and (p / "manifest.json").exists())


def test_integration_dirs_found() -> None:
    dirs = _integration_dirs()
    names = {p.name for p in dirs}
    assert UMBRELLA in names, "Dach-Integration fehlt"
    # Mindestens das Dach + ein paar Teilintegrationen
    assert len(dirs) >= 5, f"Unerwartet wenige Integrationen: {names}"


@pytest.mark.parametrize("path", _integration_dirs(), ids=lambda p: p.name)
def test_manifest_valid_and_matches_dirname(path: Path) -> None:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert "domain" in manifest, f"{path.name}: kein domain-Feld"
    assert manifest["domain"] == path.name, (
        f"{path.name}: domain={manifest['domain']} stimmt nicht mit Ordnername überein"
    )
    assert "name" in manifest and manifest["name"]
    assert "version" in manifest and manifest["version"]


def test_domains_unique() -> None:
    domains = [
        json.loads((p / "manifest.json").read_text(encoding="utf-8"))["domain"]
        for p in _integration_dirs()
    ]
    assert len(domains) == len(set(domains)), f"doppelte Domains: {domains}"


def test_no_cross_integration_imports() -> None:
    """Keine Teilintegration importiert eine andere via custom_components.<x>."""
    domains = {p.name for p in _integration_dirs()}
    offenders: list[str] = []
    for integ in _integration_dirs():
        own = integ.name
        for py in integ.rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.Import):
                    mods = [n.name for n in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for mod in mods:
                    if not mod.startswith("custom_components."):
                        continue
                    parts = mod.split(".")
                    if len(parts) >= 2 and parts[1] in domains and parts[1] != own:
                        offenders.append(f"{py.relative_to(REPO)} -> {mod}")
    assert not offenders, "Cross-Imports gefunden:\n" + "\n".join(offenders)


def test_umbrella_has_config_flow_and_known_members() -> None:
    umbrella = CC / UMBRELLA
    manifest = json.loads((umbrella / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("config_flow") is True
    const_src = (umbrella / "const.py").read_text(encoding="utf-8")
    assert "KNOWN_MEMBERS" in const_src
    # Smoke: die im Repo vorhandenen Teilintegrationen sollten in KNOWN_MEMBERS auftauchen.
    members_listed = {p.name for p in _integration_dirs()} - {UMBRELLA}
    for domain in members_listed:
        assert f'"{domain}"' in const_src, (
            f"{domain} ist im Repo vorhanden, aber nicht in KNOWN_MEMBERS gelistet"
        )


EXPECTED_DOMAINS: set[str] = {
    "bennis_toolbox",
    "wake_planner",
    "title_classifier",
    "benni_context",
    "benni_media_context",
    "notification_router",
    "plug_policy_engine",
    "stash_ha",
    "maw",
}

LEGACY_DOMAINS: set[str] = {
    "etm",
    "benni_notification_router",
    "benni_plug_policy",
    "stash_player",
    "media_art_wrapper",
}


def test_expected_domains_present() -> None:
    actual = {p.name for p in _integration_dirs()}
    missing = EXPECTED_DOMAINS - actual
    extra = actual - EXPECTED_DOMAINS
    assert not missing, f"fehlende Integrationen: {missing}"
    assert not extra, f"unerwartete Integrationen: {extra}"


def test_no_legacy_domain_folders() -> None:
    actual = {p.name for p in CC.iterdir() if p.is_dir()}
    leftover = LEGACY_DOMAINS & actual
    assert not leftover, f"Legacy-Ordner noch vorhanden: {leftover}"


def test_no_legacy_domain_in_manifests() -> None:
    """Kein manifest.json darf eine alte Domain als domain-Feld haben."""
    for path in _integration_dirs():
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["domain"] not in LEGACY_DOMAINS, (
            f"{path.name}/manifest.json domain={manifest['domain']} ist legacy"
        )


LEGACY_TOKENS: tuple[str, ...] = (
    "benni_notification_router",
    "benni_plug_policy",
    "stash_player",
    "media_art_wrapper",
    "etm",   # case-sensitive substring; matches "etm", "etm_", "_etm"
    "ETM",   # CONF_ETM_*, ETM_GAME_*, "ETM" in docstrings/comments
    "Etm",   # CamelCase class prefixes like EtmConfigFlow
)


def test_no_legacy_tokens_in_production_code() -> None:
    """Produktiver Code in den Teilintegrationen darf keine Legacy-Tokens
    enthalten. Erlaubt sind nur:
      - bennis_toolbox/const.py (LEGACY_DOMAINS-Mapping)
      - bennis_toolbox/status.py (Legacy-Erkennung)
      - alle Dateien in docs/ und tests/
    """
    offenders: list[str] = []
    for integ in _integration_dirs():
        for file in integ.rglob("*"):
            if not file.is_file() or file.suffix in {".pyc"}:
                continue
            if "__pycache__" in file.parts:
                continue
            rel = file.relative_to(REPO)
            # bennis_toolbox darf Legacy-Domains erwähnen (Erkennung).
            if rel.parts[:2] == ("custom_components", "bennis_toolbox"):
                continue
            try:
                src = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for token in LEGACY_TOKENS:
                # Substring-Match. 'etm' lowercase ist absichtlich strikt,
                # damit CONF_ETM_*, etm_ps5, ETM_GAME_* nicht zurückkehren.
                if token in src:
                    offenders.append(f"{rel}: contains '{token}'")
                    break
    assert not offenders, "Legacy-Tokens im Produktivcode:\n" + "\n".join(offenders)


def test_no_toolbox_domain_prefixes() -> None:
    """Teilintegrationen dürfen keinen 'toolbox_'-Präfix in der Domain führen.
    Organisatorische Zugehörigkeit gehört ins Monorepo, nicht in den Domain-Namen.
    """
    bad: list[str] = []
    for path in _integration_dirs():
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        domain = manifest["domain"]
        if domain == "bennis_toolbox":
            continue
        if domain.startswith("toolbox_") or domain.startswith("bennis_toolbox_"):
            bad.append(f"{path.name}: domain={domain}")
    assert not bad, "Verbotene toolbox_-Präfixe:\n" + "\n".join(bad)


def test_umbrella_does_not_import_members() -> None:
    """Dach-Integration darf keine Teilintegration hart importieren."""
    umbrella = CC / UMBRELLA
    member_domains = {p.name for p in _integration_dirs()} - {UMBRELLA}
    offenders: list[str] = []
    for py in umbrella.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        for d in member_domains:
            needle = f"custom_components.{d}"
            if needle in src:
                offenders.append(f"{py.relative_to(REPO)} -> {needle}")
    assert not offenders, "Dach importiert Teilintegrationen:\n" + "\n".join(offenders)
