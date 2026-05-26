"""Load benni_core_presence_state's HA-free files als synthetisches Paket."""

from __future__ import annotations

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(
    ROOT, "custom_components", "bennis_toolbox", "modules", "benni_core_presence_state"
)

pkg_name = "bcps_pure_pkg"
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
logic = _load("logic", "logic.py")

sys.modules["bcps_const"] = const
sys.modules["bcps_logic"] = logic
