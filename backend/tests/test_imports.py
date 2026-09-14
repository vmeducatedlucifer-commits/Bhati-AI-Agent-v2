"""Boot smoke test.

Every deploy failure so far was an import-time error (missing dependency,
missing symbol, bad env parsing). This test imports *every* module in the
`app` package plus the FastAPI entrypoint, so those failures show up in CI
instead of on Render.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import app

SKIP_PREFIXES: tuple[str, ...] = ()


def _module_names() -> list[str]:
    names = []
    for info in pkgutil.walk_packages(app.__path__, prefix="app."):
        if info.name.startswith(SKIP_PREFIXES):
            continue
        names.append(info.name)
    return sorted(names)


@pytest.mark.parametrize("module_name", _module_names())
def test_module_imports(module_name: str) -> None:
    importlib.import_module(module_name)


def test_app_entrypoint_builds(monkeypatch) -> None:
    """Mirrors how uvicorn loads the app on Render, including CORS_ORIGINS=*."""
    monkeypatch.setenv("CORS_ORIGINS", "*")
    main = importlib.import_module("app.main")
    routes = {getattr(route, "path", "") for route in main.app.routes}
    assert "/api/health" in routes


def test_every_router_module_exposes_router() -> None:
    from app.api import routes

    for name in routes.__all__:
        module = getattr(routes, name)
        assert hasattr(module, "router"), f"{name} has no `router`"
