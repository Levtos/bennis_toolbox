"""Re-Export der Entity-Lookup-Funktion gemäß base.ModuleProtocol."""

from __future__ import annotations

from .sensor import async_get_entities  # re-export für ModuleProtocol

__all__ = ["async_get_entities"]
