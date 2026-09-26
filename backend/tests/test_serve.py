"""
Tests for the server launcher (backend/serve.py): on Windows uvicorn must be
pointed at a selector event loop (psycopg async cannot use the default
ProactorEventLoop), and everywhere else the launcher must leave uvicorn's
own choice alone.

Run with: pytest backend/tests/test_serve.py -v
"""

import asyncio
from unittest.mock import patch

import pytest
import uvicorn
from uvicorn.importer import import_from_string

import backend.serve as serve


def test_windows_uses_the_selector_loop_factory(monkeypatch):
    monkeypatch.setattr(serve.sys, "platform", "win32")

    assert serve.loop_setting() == "backend.serve:selector_loop_factory"


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_other_platforms_keep_uvicorns_own_loop(monkeypatch, platform):
    monkeypatch.setattr(serve.sys, "platform", platform)

    assert serve.loop_setting() == "auto"


def test_the_loop_factory_returns_a_selector_loop():
    loop = serve.selector_loop_factory()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()


def test_uvicorn_resolves_the_setting_to_our_factory_in_both_run_modes():
    """The setting must be an import string uvicorn can load, and it must
    survive reload mode (which re-creates the config in a subprocess)."""
    assert import_from_string("backend.serve:selector_loop_factory") is serve.selector_loop_factory

    for reload in (False, True):
        config = uvicorn.Config(serve.APP, loop="backend.serve:selector_loop_factory", reload=reload)
        assert config.get_loop_factory() is serve.selector_loop_factory


def test_main_passes_the_loop_and_cli_options_to_uvicorn(monkeypatch):
    monkeypatch.setattr(serve.sys, "platform", "win32")

    with patch.object(serve.uvicorn, "run") as run:
        serve.main(["--port", "9000", "--reload"])

    run.assert_called_once_with(
        "backend.main:app", host="127.0.0.1", port=9000, reload=True,
        loop="backend.serve:selector_loop_factory",
    )


def test_main_defaults_match_the_documented_dev_setup(monkeypatch):
    monkeypatch.setattr(serve.sys, "platform", "linux")

    with patch.object(serve.uvicorn, "run") as run:
        serve.main([])

    run.assert_called_once_with("backend.main:app", host="127.0.0.1", port=8001, reload=False, loop="auto")
