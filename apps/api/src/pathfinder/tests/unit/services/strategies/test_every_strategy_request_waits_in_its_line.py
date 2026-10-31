from __future__ import annotations

import ast
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[4]
_STRATEGY_REQUESTS = {"get_strategy", "update_strategy", "set_saved", "delete_strategy"}
_STRATEGY_READERS = {"get_estimated_size_for_site"}


def _sends_a_strategy_request(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in _STRATEGY_READERS
    if not isinstance(func, ast.Attribute) or func.attr not in _STRATEGY_REQUESTS:
        return False
    receiver = func.value
    if isinstance(receiver, ast.Name):
        return receiver.id == "api"
    return (
        isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Name)
        and receiver.func.id == "get_strategy_api"
    )


def _holds_the_line(node: ast.AsyncWith) -> bool:
    return any(
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == "held_strategy"
        for item in node.items
        for inner in ast.walk(item.context_expr)
    )


def _requests(source: str) -> list[tuple[int, bool]]:
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    found: list[tuple[int, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _sends_a_strategy_request(node):
            continue
        held = False
        ancestor = parents.get(node)
        while ancestor is not None and not held:
            held = isinstance(ancestor, ast.AsyncWith) and _holds_the_line(ancestor)
            ancestor = parents.get(ancestor)
        found.append((node.lineno, held))
    return found


def _every_request() -> dict[str, list[tuple[int, bool]]]:
    found: dict[str, list[tuple[int, bool]]] = {}
    for path in _SOURCE_ROOT.rglob("*.py"):
        module = path.relative_to(_SOURCE_ROOT).as_posix()
        if module.startswith("tests/"):
            continue
        requests = _requests(path.read_text())
        if requests:
            found[module] = requests
    return found


def test_every_request_on_a_wdk_strategy_holds_its_line() -> None:
    outside = [
        f"{module}:{line}"
        for module, requests in _every_request().items()
        for line, held in requests
        if not held
    ]

    assert outside == []


def test_the_sweep_reads_the_modules_that_send_strategy_requests() -> None:
    swept = set(_every_request())

    assert {
        "services/strategies/sync.py",
        "services/gene_sets/strategy_genes.py",
        "services/strategies/naming.py",
        "ai/tools/standalone/execution.py",
    } <= swept
