"""See "What the test cannot see" in docs/knowledge/decisions/a-message-names-only-its-agents-tools.md."""

from __future__ import annotations

import ast
import fnmatch
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

from strategist.tests._support.agent_texts import (
    AGENT_SITES,
    BUILT,
    DISPATCH_TEXTS,
    AgentSite,
    held_on_every_site,
    reached_by,
    reached_units,
)
from strategist.tests._support.literal_reach import (
    PACKAGES,
    SKIP_GLOBS,
    all_literals,
    module_name,
    modules,
    package_root,
    references_of,
    resolve,
    skipped,
)
from strategist.tests._support.tool_names import (
    ALLOWED,
    RETIRED_TOOLS,
    all_tool_names,
    allowed_in,
    held_tool_names,
    named_tools,
)

_PYPROJECT = Path(__file__).resolve().parents[5] / "pyproject.toml"
_MOCK = "strategist.ai.models.mock"
_DISPATCH_KEYWORDS = frozenset({"work_order", "ledger_summary"})


def _strategist_units() -> list[tuple[str, ast.AST]]:
    return [
        (f"{module.name}.{name}", unit)
        for module in modules().values()
        if module.name.startswith("strategist.")
        for name, unit in module.units.items()
    ]


def test_the_agent_list_is_every_agent_the_code_builds() -> None:
    built = {
        qualname
        for qualname, unit in _strategist_units()
        for node in ast.walk(unit)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Agent"
    }

    assert built == {site.qualname for site in AGENT_SITES}


def _method_owner(method: str) -> str | None:
    owners = [
        qualname
        for qualname, unit in _strategist_units()
        if isinstance(unit, ast.ClassDef)
        and any(
            isinstance(item, ast.FunctionDef) and item.name == method
            for item in unit.body
        )
    ]
    return owners[0] if len(owners) == 1 else None


def _called(module_name: str, name: str) -> str | None:
    return resolve(f"{module_name}.{name}") or resolve(
        modules()[module_name].imports.get(name, "")
    )


def _assigned_from(module_name: str, unit: ast.AST, variable: str) -> str | None:
    return next(
        (
            _called(module_name, node.value.func.id)
            for node in ast.walk(unit)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == variable for t in node.targets)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        ),
        None,
    )


def _producers(
    module_name: str, enclosing: str, unit: ast.AST, value: ast.expr
) -> set[str]:
    if isinstance(value, ast.Name):
        params = {
            arg.arg
            for fn in ast.walk(unit)
            if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef)
            for arg in [*fn.args.args, *fn.args.kwonlyargs]
        }
        return set() if value.id in params else {enclosing}
    found: set[str] = set()
    for call in ast.walk(value):
        match call:
            case ast.Call(func=ast.Name(id=name)):
                resolved = _called(module_name, name)
                if resolved is not None:
                    found.add(resolved)
            case ast.Call(func=ast.Attribute(value=ast.Name(id=variable))):
                made = _assigned_from(module_name, unit, variable)
                if made is not None:
                    found.add(made)
            case ast.Call(func=ast.Attribute(attr=method)):
                owner = _method_owner(method)
                if owner is not None:
                    found.add(owner)
            case _:
                pass
    return found


def test_the_dispatch_texts_are_every_text_a_sub_agent_is_sent() -> None:
    found: set[str] = set()
    for module in modules().values():
        if not module.name.startswith("strategist."):
            continue
        for name, unit in module.units.items():
            for call in ast.walk(unit):
                if not isinstance(call, ast.Call):
                    continue
                values = [k.value for k in call.keywords if k.arg in _DISPATCH_KEYWORDS]
                if isinstance(call.func, ast.Name) and call.func.id == "PhaseRun":
                    values.extend(call.args[1:2])
                for value in values:
                    found |= _producers(
                        module.name, f"{module.name}.{name}", unit, value
                    )

    assert found == set(DISPATCH_TEXTS)


def test_the_scanned_roots_are_the_pinned_distributions() -> None:
    sources = tomllib.loads(_PYPROJECT.read_text())["tool"]["uv"]["sources"]
    imported = {
        node.module.split(".")[0]
        if isinstance(node, ast.ImportFrom) and node.module
        else alias.name.split(".")[0]
        for module in modules().values()
        if module.name.startswith("strategist.")
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    pinned = {
        package
        for package, distributions in packages_distributions().items()
        if set(distributions) & set(sources) and package in imported
    }

    assert set(PACKAGES) == {"strategist", *pinned}


def test_every_skip_glob_matches_a_file_and_hides_no_reached_module() -> None:
    root = package_root("strategist")
    files = [str(path) for path in root.rglob("*.py")]
    hidden = {module_name(root, Path(path))[0] for path in files if skipped(Path(path))}
    referenced = {
        ref
        for role in BUILT
        for unit in reached_units(role)
        for ref in references_of(unit)
    }
    reached_hidden = sorted(
        name
        for name in hidden
        if not (name == _MOCK or name.startswith(f"{_MOCK}."))
        and any(ref == name or ref.startswith(f"{name}.") for ref in referenced)
    )

    assert [g for g in SKIP_GLOBS if not fnmatch.filter(files, g)] == []
    assert reached_hidden == []


@pytest.mark.parametrize(
    ("unit", "roles"),
    [
        (
            "strategist.jobs.impls.eda_compute_impl.compute_result",
            ("explore", "lead"),
        ),
        (
            "strategist.domain.strategy.staleness.StaleBuild",
            ("execution", "lead", "verification"),
        ),
        (
            "strategist.domain.exchanges.approval_card",
            ("execution", "frame", "verification"),
        ),
    ],
)
def test_the_reach_holds_completions_attribute_calls_and_node_state(
    unit: str, roles: tuple[str, ...]
) -> None:
    assert [role for role in roles if unit not in reached_units(role)] == []


def test_no_retired_name_is_a_tool() -> None:
    assert RETIRED_TOOLS & all_tool_names() == frozenset()


def test_the_allowlist_holds_only_sentences_that_exist() -> None:
    texts = {site.role: site.texts() for site in AGENT_SITES if site.build is None}
    missing = [
        (agent, sentence)
        for agent, _, sentence, _ in ALLOWED
        if not any(
            sentence in text
            for text in texts.get(agent)
            or [literal.text for literal in reached_by(agent)]
        )
    ]

    assert missing == []


def test_a_name_inside_a_longer_word_is_not_a_mention() -> None:
    assert named_tools("call research_web_search") == {"research_web_search"}
    assert named_tools("strategy.delete_step(x)") == frozenset()
    assert named_tools("step_id=3") == frozenset()
    assert named_tools("cites audit_gene_length:EXA_0003") == frozenset()
    assert named_tools("set_criterion: binds a value") == {"set_criterion"}


def test_a_one_word_tool_counts_only_as_a_call_or_in_backticks() -> None:
    assert named_tools("a note about a set") == frozenset()
    assert named_tools("call note(...)") == {"note"}
    assert named_tools("`think`") == {"think"}


@pytest.mark.parametrize("site", AGENT_SITES, ids=lambda site: site.qualname)
def test_an_agents_static_texts_name_only_its_tools(site: AgentSite) -> None:
    held = frozenset() if site.build is None else held_on_every_site(site.build())

    foreign = {
        name
        for text in site.texts()
        for name in named_tools(text) - held - allowed_in(text, site.role)
    }
    retired = {name for text in site.texts() for name in named_tools(text)}

    assert sorted(foreign) == []
    assert sorted(retired & RETIRED_TOOLS) == []


@pytest.mark.parametrize("role", sorted(BUILT))
def test_a_literal_an_agent_can_receive_names_only_its_tools(role: str) -> None:
    held = held_tool_names(BUILT[role]())

    foreign = [
        f"{literal.path.name}:{literal.line} {sorted(unheld)}"
        for literal in reached_by(role)
        if (unheld := named_tools(literal.text) - held - allowed_in(literal.text, role))
    ]

    assert foreign == []


def test_no_literal_names_a_retired_tool() -> None:
    named = [
        f"{literal.path.name}:{literal.line}"
        for literal in all_literals()
        if named_tools(literal.text) & RETIRED_TOOLS
    ]

    assert named == []
