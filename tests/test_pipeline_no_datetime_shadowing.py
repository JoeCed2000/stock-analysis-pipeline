"""Regression tests for Python local-import shadowing in pipeline functions."""

from __future__ import annotations

import ast
from pathlib import Path


def _function_node(module: ast.Module, name: str) -> ast.FunctionDef:
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


def test_add_earnings_deep_dive_does_not_shadow_datetime_import():
    """No local `from datetime import datetime` inside the deep-dive function.

    Python treats imports inside a function as assignments. A local datetime import
    in one branch shadows the module-level datetime everywhere in the function,
    which caused post-generation validation to crash at datetime.now(timezone.utc).
    """
    path = Path(__file__).resolve().parents[1] / "backend" / "pipeline.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    func = _function_node(module, "_add_earnings_deep_dive_if_transcript")

    offenders = []
    for node in ast.walk(func):
        if isinstance(node, ast.ImportFrom) and node.module == "datetime":
            imported = {alias.name for alias in node.names}
            if "datetime" in imported:
                offenders.append(node.lineno)

    assert offenders == [], (
        "Local datetime import shadows module-level datetime inside "
        f"_add_earnings_deep_dive_if_transcript at lines {offenders}"
    )
