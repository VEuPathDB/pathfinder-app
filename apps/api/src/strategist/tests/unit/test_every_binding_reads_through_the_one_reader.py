from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache, cached_property
from importlib.util import find_spec
from pathlib import Path

from strategist.tests.unit.ai.tools.test_every_binding_path_reads_a_held_child_alike import (
    PATHS,
    STATES_EVERY_VALUE,
)

SOURCE = Path(__file__).parents[2]


def _package_root(name: str) -> Path:
    spec = find_spec(name)
    if spec is None or spec.origin is None:
        msg = f"{name} is not installed as a package with a source file"
        raise LookupError(msg)
    return Path(spec.origin).parent


MCP_SOURCE = _package_root("veupathdb_mcp")
LOW_LEVEL = frozenset({"read_under_parents", "read_declared", "read_stated_values"})
READERS = frozenset(
    {
        "ai/tools/standalone/_stated_values.py",
        "ai/tools/standalone/_frame_proposals.py",
        "services/strategies/sheet_params.py",
    }
)
TOOLS: dict[str, frozenset[str]] = {
    "frame_rebind": frozenset({"ai/tools/standalone/frame_spec.py:_bind_the_search"}),
    "variant": frozenset({"ai/tools/standalone/_variant_targets.py:resolved_variants"}),
    "update_leaf_params": frozenset(
        {"ai/tools/standalone/strategy_edits.py:update_leaf_params"}
    ),
    "typed_operation": frozenset({"ai/tools/standalone/strategy.py:apply_operations"}),
    "options_read": frozenset(
        {"ai/tools/standalone/catalog_discovery.py:get_parameter_options"}
    ),
    "card_pick": frozenset({"ai/lead/readings.py:picks_their_criteria_refuse"}),
    "build_strategy": frozenset(
        {
            "ai/tools/standalone/strategy.py:build_strategy",
            "ai/tools/standalone/strategy_edits.py:replace_subtree",
        }
    ),
    "control_test": frozenset(
        {"ai/tools/standalone/experiment.py:run_control_tests_on_search"}
    ),
}


BIND_VALUES = "strategist.domain.strategy.value_binding.bind_values"
ALREADY_BOUND: dict[str, str] = {
    "ai/tools/standalone/_frame_sources.py:bound_values": "read by the reader",
    "domain/strategy/spec_hydration.py:_structure_of": "held by the site",
    "domain/strategy/spec_replay.py:criterion_restated": "replayed from the spec",
    "domain/strategy/spec_replay.py:criterion_rebound": "replayed from the spec",
    "services/experiment/reading_count.py:_criterion": "measured on a spec",
    "services/separation/offer.py:_criterion": "measured on a spec",
}


@dataclass(frozen=True)
class Module:
    path: str
    tree: ast.Module

    @cached_property
    def imported(self) -> dict[str, str]:
        names: dict[str, str] = {}
        for node in ast.walk(self.tree):
            match node:
                case ast.ImportFrom(module=str(module), names=aliases):
                    names |= {a.name: f"{module}.{a.name}" for a in aliases}
                case ast.Import(names=aliases):
                    names |= {
                        a.name.split(".")[0]: a.name.split(".")[0] for a in aliases
                    }
                case _:
                    pass
        return names

    def functions(self) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
        def walk(
            node: ast.AST, prefix: str
        ) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
            for child in ast.iter_child_nodes(node):
                match child:
                    case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name):
                        yield f"{prefix}{name}", child
                        yield from walk(child, f"{prefix}{name}.")
                    case ast.ClassDef(name=name):
                        yield from walk(child, f"{prefix}{name}.")
                    case _:
                        pass

        return walk(self.tree, "")

    def called(self, node: ast.AST) -> set[str]:
        imported = self.imported
        found: set[str] = set()
        for call in ast.walk(node):
            match call:
                case ast.Call(func=ast.Name(id=name)):
                    found.add(imported.get(name, f"{self.path}.{name}"))
                case ast.Call(func=ast.Attribute(value=ast.Name(id=owner), attr=name)):
                    found.add(f"{imported.get(owner, owner)}.{name}")
                case _:
                    pass
        return found

    def referenced(self) -> set[str]:
        imported = self.imported
        found = set(imported.values())
        for node in ast.walk(self.tree):
            match node:
                case ast.Attribute(value=ast.Name(id=owner), attr=name) if (
                    owner in imported
                ):
                    found.add(f"{imported[owner]}.{name}")
                case _:
                    pass
        return found

    def dynamic_reads(self) -> list[int]:
        modules = {
            local
            for local, qualified in self.imported.items()
            if qualified.split(".")[0] in {"veupathdb_mcp", "veupathdb", "strategist"}
        }
        return [
            node.lineno
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and node.args
            and _root(node.args[0]) in modules
        ]


def _root(node: ast.expr) -> str:
    match node:
        case ast.Name(id=name):
            return name
        case ast.Attribute(value=inner):
            return _root(inner)
        case _:
            return ""


@cache
def modules(root: Path) -> list[Module]:
    return [
        Module(path.relative_to(root).as_posix(), ast.parse(path.read_text()))
        for path in sorted(root.rglob("*.py"))
        if "tests" not in path.relative_to(root).parts
    ]


def _last(qualified: str) -> str:
    return qualified.rsplit(".", 1)[-1]


@cache
def binders(root: Path = MCP_SOURCE) -> frozenset[str]:
    calls: dict[str, set[str]] = {}
    for module in modules(root):
        for name, node in module.functions():
            if "." not in name:
                calls.setdefault(name, set()).update(map(_last, module.called(node)))
    found = set(LOW_LEVEL)
    grown = True
    while grown:
        added = {name for name, made in calls.items() if made & found} - found
        found |= added
        grown = bool(added)
    return frozenset(name for name in found if not name.startswith("_"))


def _is_binder(qualified: str, bound: frozenset[str]) -> bool:
    return qualified.startswith("veupathdb") and _last(qualified) in bound


def _dotted(path: str) -> str:
    return "strategist." + path.removesuffix(".py").replace("/", ".")


def entries(root: Path = SOURCE, readers: frozenset[str] = READERS) -> frozenset[str]:
    bound = binders()
    found: set[str] = set()
    for module in modules(root):
        if module.path not in readers:
            continue
        calls = {
            name: module.called(node)
            for name, node in module.functions()
            if "." not in name
        }
        reach = {
            name
            for name, made in calls.items()
            if any(_is_binder(c, bound) for c in made)
        }
        grown = True
        while grown:
            added = {
                name for name, made in calls.items() if {_last(c) for c in made} & reach
            } - reach
            reach |= added
            grown = bool(added)
        found |= {
            f"{_dotted(module.path)}.{name}"
            for name in reach
            if not name.startswith("_")
        }
    return frozenset(found)


def callers(root: Path = SOURCE, readers: frozenset[str] = READERS) -> set[str]:
    reached = entries(root, readers)
    return {
        f"{module.path}:{name}"
        for module in modules(root)
        if module.path not in readers
        for name, node in module.functions()
        if module.called(node) & reached
    }


def escapes(root: Path = SOURCE, readers: frozenset[str] = READERS) -> list[str]:
    bound = binders()
    found: list[str] = []
    for module in modules(root):
        if module.path in readers:
            continue
        found += [
            f"{module.path}: {name}"
            for name in sorted(module.referenced())
            if _is_binder(name, bound)
        ]
        found += [f"{module.path}:{line}: getattr" for line in module.dynamic_reads()]
    return found


def test_every_writer_of_bound_values_is_named() -> None:
    writers = {
        f"{module.path}:{name}"
        for module in modules(SOURCE)
        for name, node in module.functions()
        if BIND_VALUES in module.called(node)
    }

    assert writers == set(ALREADY_BOUND)


def test_the_mcp_binders_are_derived_from_its_source() -> None:
    assert {"read_stated_parameters", "read_stated_context"} <= binders()


def test_only_the_reader_modules_reach_a_binder() -> None:
    assert escapes() == []


def test_every_tool_that_binds_is_a_path_of_the_binding_test() -> None:
    mapped = set().union(*TOOLS.values())

    assert (sorted(callers() - mapped), sorted(mapped - callers())) == ([], [])
    assert set(TOOLS) == set(PATHS) | set(STATES_EVERY_VALUE)


_READER = "from veupathdb_mcp.catalog import read_under_parents\n\n\nasync def typed_values():\n    return await read_under_parents()\n"
_STATED = "ai/tools/standalone/_stated_values.py"


def _tree(root: Path, files: dict[str, str]) -> Path:
    for path, text in {_STATED: _READER, **files}.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    return root


def test_a_new_reader_function_and_its_caller_are_found(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            _STATED: _READER
            + "\n\nasync def bind_under():\n    return await read_under_parents()\n",
            "ai/tools/new_tool.py": "from strategist.ai.tools.standalone._stated_values import bind_under\n\n\nasync def tool():\n    return await bind_under()\n",
        },
    )

    assert callers(root, frozenset({_STATED})) == {"ai/tools/new_tool.py:tool"}


def test_a_new_tool_in_a_mapped_module_is_found(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "ai/tools/standalone/strategy.py": "from strategist.ai.tools.standalone._stated_values import typed_values\n\n\nasync def build_strategy():\n    return await typed_values()\n\n\nasync def another_tool():\n    return await typed_values()\n",
        },
    )

    assert callers(root, frozenset({_STATED})) == {
        "ai/tools/standalone/strategy.py:build_strategy",
        "ai/tools/standalone/strategy.py:another_tool",
    }


def test_an_mcp_wrapper_that_binds_is_found(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {"ai/context.py": "from veupathdb_mcp.catalog import read_stated_context\n"},
    )

    assert escapes(root, frozenset({_STATED})) == [
        "ai/context.py: veupathdb_mcp.catalog.read_stated_context"
    ]


def test_a_binder_read_by_getattr_is_found(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "ai/dynamic.py": "import veupathdb_mcp.catalog\n\nREAD = getattr(veupathdb_mcp.catalog, 'read_' + 'under_parents')\n",
        },
    )

    assert escapes(root, frozenset({_STATED})) == ["ai/dynamic.py:3: getattr"]
