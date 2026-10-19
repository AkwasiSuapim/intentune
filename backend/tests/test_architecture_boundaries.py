"""Dependency-direction guard: inner layers must not import storage or delivery frameworks.

The domain is pure (spec §4), and the application layer reaches storage only
through ports. Only src/intentune/persistence/ (and backend/alembic/) may
import SQLAlchemy or Alembic.

Every .py file under a layer is checked, including files in subpackages, and
relative imports are resolved to absolute module names before checking, so
`from ..persistence import db` is caught the same way as
`from src.intentune.persistence import db`.
"""

import ast
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_INNER_LAYERS = ("domain", "ports", "application")
_FRAMEWORKS = {"sqlalchemy", "alembic", "sqlite3", "fastapi", "starlette", "pydantic"}
_OUTER_PACKAGES = ("src.intentune.persistence", "src.intentune.adapters")


def _imported_modules(source, module_name, is_package):
    """Absolute dotted names of the modules the import statements in `source` refer to.

    Relative imports are resolved against `module_name`. For `from X import Y`
    both X and X.Y are returned, because Y may itself be a submodule.
    """
    package = module_name.split(".") if is_package else module_name.split(".")[:-1]
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package[: len(package) - node.level + 1]
                base = ".".join(anchor + ([node.module] if node.module else []))
            else:
                base = node.module
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return names


def _imports_by_file(backend_root, layer):
    """{path relative to backend_root: imported module names}, for every .py file in the layer, recursively."""
    imports = {}
    for path in sorted((backend_root / "src" / "intentune" / layer).rglob("*.py")):
        parts = path.relative_to(backend_root).with_suffix("").parts
        is_package = parts[-1] == "__init__"
        module_name = ".".join(parts[:-1] if is_package else parts)
        imports[path.relative_to(backend_root).as_posix()] = _imported_modules(
            path.read_text(encoding="utf-8"), module_name, is_package
        )
    return imports


def _is_within(name, package):
    return name == package or name.startswith(package + ".")


def _framework_violations(imports):
    return sorted(
        f"{path} imports {name}" for path, names in imports.items() for name in names if name.split(".")[0] in _FRAMEWORKS
    )


def _outer_package_violations(imports):
    return sorted(
        f"{path} imports {name}"
        for path, names in imports.items()
        for name in names
        if any(_is_within(name, package) for package in _OUTER_PACKAGES)
    )


def _outside_domain_violations(imports):
    return sorted(
        f"{path} imports {name}"
        for path, names in imports.items()
        for name in names
        if _is_within(name, "src") and not _is_within(name, "src.intentune.domain")
    )


# --- The rules, applied to the real source tree ------------------------------


@pytest.mark.parametrize("layer", _INNER_LAYERS)
def test_inner_layers_import_no_storage_or_delivery_framework(layer):
    imports = _imports_by_file(_BACKEND, layer)

    assert imports, f"no Python files found under {layer}/"
    assert _framework_violations(imports) == []


@pytest.mark.parametrize("layer", _INNER_LAYERS)
def test_inner_layers_do_not_import_persistence_or_adapters(layer):
    imports = _imports_by_file(_BACKEND, layer)

    assert imports, f"no Python files found under {layer}/"
    assert _outer_package_violations(imports) == []


def test_domain_imports_nothing_outside_the_domain():
    imports = _imports_by_file(_BACKEND, "domain")

    assert imports, "no Python files found under domain/"
    assert _outside_domain_violations(imports) == []


# --- The checker itself --------------------------------------------------------


@pytest.mark.parametrize(
    "source, module_name, is_package, expected",
    [
        ("from ..persistence.db import create_database_engine", "src.intentune.application.local_listener", False, "src.intentune.persistence.db"),
        ("from .. import persistence", "src.intentune.application.local_listener", False, "src.intentune.persistence"),
        ("from ...persistence import models", "src.intentune.application.sessions.start", False, "src.intentune.persistence.models"),
        ("from . import helpers", "src.intentune.domain.session", True, "src.intentune.domain.session.helpers"),
        ("from .listener import ListenerProfile", "src.intentune.domain.models", False, "src.intentune.domain.listener"),
        ("import sqlalchemy.orm", "src.intentune.ports.catalog", False, "sqlalchemy.orm"),
        ("from sqlalchemy.orm import Session", "src.intentune.ports.catalog", False, "sqlalchemy.orm"),
    ],
    ids=[
        "parent-relative-module",
        "parent-relative-package-name",
        "relative-from-subpackage",
        "relative-inside-package-init",
        "sibling-relative",
        "absolute-import",
        "absolute-from-import",
    ],
)
def test_imports_resolve_to_absolute_module_names(source, module_name, is_package, expected):
    assert expected in _imported_modules(source, module_name, is_package)


def _write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_violations_in_nested_subpackages_and_relative_imports_are_caught(tmp_path):
    intentune = tmp_path / "src" / "intentune"
    _write(intentune / "domain" / "session" / "__init__.py", "")
    _write(intentune / "domain" / "session" / "state.py", "import sqlalchemy\nfrom ...ports import catalog\n")
    _write(intentune / "domain" / "session" / "clean.py", "from ..models import MusicCandidate\n")
    _write(intentune / "application" / "use_cases" / "deep" / "start.py", "from ....persistence.db import create_database_engine\n")
    _write(intentune / "ports" / "nested" / "repo.py", "from ... import adapters\n")

    domain = _imports_by_file(tmp_path, "domain")
    application = _imports_by_file(tmp_path, "application")
    ports = _imports_by_file(tmp_path, "ports")

    assert _framework_violations(domain) == ["src/intentune/domain/session/state.py imports sqlalchemy"]
    assert _outside_domain_violations(domain) == [
        "src/intentune/domain/session/state.py imports src.intentune.ports",
        "src/intentune/domain/session/state.py imports src.intentune.ports.catalog",
    ]
    assert _outer_package_violations(application) == [
        "src/intentune/application/use_cases/deep/start.py imports src.intentune.persistence.db",
        "src/intentune/application/use_cases/deep/start.py imports src.intentune.persistence.db.create_database_engine",
    ]
    assert _outer_package_violations(ports) == ["src/intentune/ports/nested/repo.py imports src.intentune.adapters"]
