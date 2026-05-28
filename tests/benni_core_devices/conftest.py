"""Load benni_core_devices' HA-free files als synthetisches Paket.

Pattern analog tests/benni_core_user_state/conftest.py.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(
    ROOT, "custom_components", "bennis_toolbox", "modules", "benni_core_devices"
)

pkg_name = "bcd_pure_pkg"
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


# Reihenfolge wichtig: const → device_types → logic (logic importiert const).
const = _load("const", "const.py")
device_types = _load("device_types", "device_types.py")
logic = _load("logic", "logic.py")

sys.modules["bcd_const"] = const
sys.modules["bcd_device_types"] = device_types
sys.modules["bcd_logic"] = logic
