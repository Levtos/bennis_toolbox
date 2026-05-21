"""Tests for StashClient transport layer using a fake aiohttp session.

We exercise the GraphQL POST path, header injection, base-URL extraction,
error mapping (HTTP non-200 → StashError, GraphQL `errors` field →
StashError), and count/version helpers.
"""

from __future__ import annotations

import asyncio
import json
from functools import wraps
from typing import Any

import pytest

import sh_client as M


def _run(coro_fn):
    @wraps(coro_fn)
    def _wrapper(*args, **kwargs):
        return asyncio.run(coro_fn(*args, **kwargs))
    return _wrapper


class _FakeResponse:
    def __init__(self, status: int, body: Any):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def json(self):
        return self._body

    async def text(self):
        return json.dumps(self._body) if not isinstance(self._body, str) else self._body


class _FakeSession:
    def __init__(self, responses):
        # responses: list of (status, body)
        self._responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, *, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": dict(headers or {})})
        if not self._responses:
            raise AssertionError("No more fake responses queued")
        status, body = self._responses.pop(0)
        return _FakeResponse(status, body)


# --------------------------------------------------------- url + headers


def test_client_strips_trailing_slash_and_derives_base():
    session = _FakeSession([])
    c = M.StashClient("https://stash.example.com:8443/graphql/", session)
    assert c.stash_url == "https://stash.example.com:8443"


def test_client_base_url_when_endpoint_lacks_graphql_suffix():
    session = _FakeSession([])
    c = M.StashClient("https://other.example/api", session)
    # If endpoint does not end with /graphql, the base is the same string
    # (no `/graphql` suffix to strip).
    assert c.stash_url == "https://other.example/api"


def test_client_headers_include_api_key_when_set():
    session = _FakeSession([])
    c = M.StashClient("https://x/graphql", session, api_key="secret")
    assert c._headers() == {"ApiKey": "secret"}


def test_client_headers_empty_when_no_api_key():
    session = _FakeSession([])
    c = M.StashClient("https://x/graphql", session, api_key="")
    assert c._headers() == {}


# --------------------------------------------------------- _post


@_run
async def test_post_passes_payload_and_headers():
    session = _FakeSession([(200, {"data": {"version": {"version": "0.31.1"}}})])
    c = M.StashClient("https://x/graphql", session, api_key="k")
    data = await c._post("query { version { version } }")
    assert data["data"]["version"]["version"] == "0.31.1"
    call = session.calls[0]
    assert call["url"] == "https://x/graphql"
    assert call["json"]["query"].strip().startswith("query")
    assert call["headers"] == {"ApiKey": "k"}


@_run
async def test_post_raises_on_non_200():
    session = _FakeSession([(500, "boom")])
    c = M.StashClient("https://x/graphql", session)
    with pytest.raises(M.StashError, match="HTTP 500"):
        await c._post("query { x }")


@_run
async def test_post_raises_on_graphql_errors_key():
    session = _FakeSession([(200, {"errors": [{"message": "nope"}]})])
    c = M.StashClient("https://x/graphql", session)
    with pytest.raises(M.StashError, match="GraphQL errors"):
        await c._post("query { x }")


@_run
async def test_post_allow_errors_returns_payload_with_errors():
    """`_post_allow_errors` must surface the body even when GraphQL signals
    partial errors — used for renamed/missing fields like findGroups."""
    session = _FakeSession([(200, {"errors": [{"message": "no such field"}]})])
    c = M.StashClient("https://x/graphql", session)
    data = await c._post_allow_errors("query { findGroups { count } }")
    assert "errors" in data


# --------------------------------------------------------- counters + version


@_run
async def test_get_scenes_count_returns_int():
    session = _FakeSession([(200, {"data": {"findScenes": {"count": 42}}})])
    c = M.StashClient("https://x/graphql", session)
    assert await c.get_scenes_count() == 42


@_run
async def test_get_movies_count_prefers_find_groups():
    session = _FakeSession([(200, {"data": {"findGroups": {"count": 7}}})])
    c = M.StashClient("https://x/graphql", session)
    assert await c.get_movies_count() == 7


@_run
async def test_get_movies_count_falls_back_to_find_movies():
    session = _FakeSession([
        # First attempt: findGroups errors out.
        (200, {"errors": [{"message": "no field"}]}),
        # Fallback: findMovies works.
        (200, {"data": {"findMovies": {"count": 3}}}),
    ])
    c = M.StashClient("https://x/graphql", session)
    assert await c.get_movies_count() == 3


@_run
async def test_get_movies_count_returns_zero_when_both_fail():
    session = _FakeSession([
        (200, {"errors": [{"message": "no findGroups"}]}),
        (200, {"errors": [{"message": "no findMovies"}]}),
    ])
    c = M.StashClient("https://x/graphql", session)
    assert await c.get_movies_count() == 0


@_run
async def test_get_version_returns_string_or_none():
    session = _FakeSession([
        (200, {"data": {"version": {"version": "0.31.1"}}}),
        (200, {"data": {"version": None}}),
    ])
    c = M.StashClient("https://x/graphql", session)
    assert await c.get_version() == "0.31.1"
    assert await c.get_version() is None
