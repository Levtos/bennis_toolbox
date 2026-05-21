"""Async GraphQL client for the Stash server.

Pure transport layer: everything is async + awaits an aiohttp ClientSession.
No HA imports beyond the type-hinted session. The session is injected so
tests can replace it with a fake.
"""
from __future__ import annotations

import asyncio
from typing import Any


class StashError(Exception):
    """Base error for Stash API."""


class StashClient:
    """Simple async GraphQL client for Stash."""

    def __init__(self, graphql_url: str, session: Any, api_key: str = "") -> None:
        self._url = graphql_url.rstrip("/")
        self._session = session
        self._api_key = (api_key or "").strip()
        # Stash returns asset URLs based on its own hostname; we keep the
        # base (everything except `/graphql`) for url-rewriting in the
        # coordinator.
        if self._url.endswith("/graphql"):
            self._base_url = self._url[: -len("/graphql")]
        else:
            self._base_url = self._url

    @property
    def stash_url(self) -> str:
        return self._base_url

    def _headers(self) -> dict:
        return {"ApiKey": self._api_key} if self._api_key else {}

    async def _post(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        async with asyncio.timeout(10):
            async with self._session.post(
                self._url, json=payload, headers=self._headers()
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise StashError(f"HTTP {resp.status}: {text}")
                data = await resp.json()
        if "errors" in data:
            raise StashError(f"GraphQL errors: {data['errors']}")
        return data

    async def _post_allow_errors(self, query: str) -> dict[str, Any]:
        """Variant that does not raise on partial GraphQL errors; used for
        endpoints that frequently return harmless errors (e.g. metadata
        mutations on idle Stash instances)."""
        payload = {"query": query}
        async with asyncio.timeout(10):
            async with self._session.post(
                self._url, json=payload, headers=self._headers()
            ) as resp:
                if resp.status != 200:
                    raise StashError(f"HTTP {resp.status}")
                return await resp.json()

    # ----- queries -----
    async def validate(self) -> None:
        await self._post("query { version { version } }")

    async def get_version(self) -> str | None:
        data = await self._post("query { version { version } }")
        try:
            return str(data["data"]["version"]["version"])
        except (KeyError, TypeError):
            return None

    async def _count(self, root: str) -> int:
        data = await self._post(f"query {{ {root} {{ count }} }}")
        return int(data["data"][root]["count"])

    async def get_scenes_count(self) -> int:
        return await self._count("findScenes")

    async def get_movies_count(self) -> int:
        # Stash renamed findMovies → findGroups; try both, allowing errors.
        raw = await self._post_allow_errors("query { findGroups { count } }")
        try:
            return int(raw["data"]["findGroups"]["count"])
        except (KeyError, TypeError, ValueError):
            pass
        raw2 = await self._post_allow_errors("query { findMovies { count } }")
        try:
            return int(raw2["data"]["findMovies"]["count"])
        except (KeyError, TypeError, ValueError):
            return 0

    async def get_performers_count(self) -> int:
        return await self._count("findPerformers")

    async def get_studios_count(self) -> int:
        return await self._count("findStudios")

    async def get_tags_count(self) -> int:
        return await self._count("findTags")

    async def get_images_count(self) -> int:
        return await self._count("findImages")

    async def get_galleries_count(self) -> int:
        return await self._count("findGalleries")

    async def get_markers_count(self) -> int:
        return await self._count("findSceneMarkers")

    # ----- mutations -----
    async def generate_screenshot(self, scene_id: str) -> None:
        await self._post_allow_errors(
            f'mutation {{ sceneGenerateScreenshot(id: "{scene_id}") }}'
        )

    async def save_activity(self, scene_id: str, position: float) -> None:
        await self._post_allow_errors(
            f'mutation {{ sceneSaveActivity(id: "{scene_id}", resume_time: {position}) }}'
        )

    async def metadata_scan(self) -> None:
        await self._post("mutation { metadataScan(input:{}) }")

    async def metadata_clean(self) -> None:
        await self._post('mutation { metadataClean(input: {dryRun: false, paths: ""}) }')

    async def metadata_generate(self) -> None:
        await self._post("mutation { metadataGenerate(input: {}) }")

    async def metadata_auto_tag(self) -> None:
        await self._post("mutation { metadataAutoTag(input: {}) }")

    async def metadata_identify(self) -> None:
        await self._post(
            'mutation { metadataIdentify(input: { sources: '
            '[{ source: { stash_box_endpoint: "https://stashdb.org/graphql" } }] }) }'
        )
