from __future__ import annotations

import ast
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _relative_imports(module: str) -> set[str]:
    tree = ast.parse((ROOT / f"{module}.py").read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def test_domain_models_do_not_import_application_or_transport_layers():
    assert _relative_imports("models") == set()


def test_storage_adapter_depends_only_on_domain_contracts():
    assert _relative_imports("storage") <= {"models"}


def test_projection_stays_below_application_and_transport_layers():
    assert _relative_imports("projection") <= {"models", "storage"}


def test_application_service_does_not_depend_on_fastapi_or_websocket_transport():
    assert _relative_imports("hermes_client") <= {"models", "projection"}


def test_fastapi_module_is_the_composition_root_for_outer_adapters():
    assert {"auth", "hermes_client", "projection", "storage", "websocket"} <= _relative_imports("main")
