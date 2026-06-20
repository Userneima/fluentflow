from __future__ import annotations

import ast
import builtins
import importlib
from pathlib import Path
import symtable


def test_router_h_helper_references_exist() -> None:
    """Route modules import server_helpers as H; every H.xxx reference must exist."""
    helpers = importlib.import_module("backend.core.server_helpers")
    missing: list[str] = []

    for path in sorted(Path("backend/routers").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "H"
                and not hasattr(helpers, node.attr)
            ):
                missing.append(f"{path}:{node.lineno} H.{node.attr}")

    assert missing == []


def test_router_job_event_hub_references_go_through_helpers() -> None:
    offenders: list[str] = []

    for path in sorted(Path("backend/routers").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "JobEventHub":
                offenders.append(f"{path}:{node.lineno} JobEventHub")

    assert offenders == []


def test_router_global_references_are_imported_or_defined() -> None:
    builtins_and_runtime = set(dir(builtins)) | {
        "__annotations__",
        "__builtins__",
        "__file__",
        "__name__",
        "__package__",
    }
    offenders: list[str] = []

    for path in sorted(Path("backend/routers").glob("*.py")):
        table = symtable.symtable(path.read_text(encoding="utf-8"), str(path), "exec")
        module_names = {
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_imported() or symbol.is_assigned() or symbol.is_namespace()
        }

        def walk(scope: symtable.SymbolTable) -> None:
            for child in scope.get_children():
                for symbol in child.get_symbols():
                    name = symbol.get_name()
                    if (
                        symbol.is_global()
                        and symbol.is_referenced()
                        and name not in module_names
                        and name not in builtins_and_runtime
                    ):
                        offenders.append(f"{path}:{child.get_name()} references undefined global {name}")
                walk(child)

        walk(table)

    assert offenders == []
