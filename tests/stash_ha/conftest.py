"""Load stash_ha's HA-free files (const, playback_logic, client) as a
synthetic package so they can be tested without homeassistant."""

from __future__ import annotations

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(
    ROOT, "custom_components", "bennis_toolbox", "modules", "stash_ha"
)

pkg_name = "sh_pure_pkg"
pkg = types.ModuleType(pkg_name)
pkg.__path__ = [PKG_DIR]
sys.modules[pkg_name] = pkg


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.{modname}", os.path.join(PKG_DIR, filename)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{pkg_name}.{modname}"] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const", "const.py")
playback_logic = _load("playback_logic", "playback_logic.py")
client_mod = _load("client", "client.py")

sys.modules["sh_const"] = const
sys.modules["sh_playback"] = playback_logic
sys.modules["sh_client"] = client_mod
