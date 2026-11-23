from __future__ import annotations

import ast
import fnmatch
import functools
import importlib.util
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

PACKAGES = ("strategist", "veupathdb", "veupathdb_mcp", "assistant_core")
SKIP_GLOBS = ("*/tests/*", "*/devtools/*", "*/ai/models/mock/*")
STATE_MODELS = "strategist.domain."
GRAPH_NODES = "strategist.ai.graph."
DURABLE_REGISTRATION = "assistant_core.tasks.declaration.register_durable_impl"
_LOG_CALLS = frozenset({"debug", "info", "warning", "error", "exception", "critical"})


@dataclass(frozen=True)
class Literal:
    path: Path
    line: int
    enclosing: str
    text: str


@dataclass
class _Module:
    name: str
    path: Path
    is_package: bool
    tree: ast.Module
    imports: dict[str, str] = field(default_factory=dict)
    units: dict[str, ast.AST] = field(default_factory=dict)
    loose: list[ast.stmt] = field(default_factory=list)


def package_root(package: str) -> Path:
    spec = importlib.util.find_spec(package)
    assert spec is not None
    assert spec.submodule_search_locations is not None
    return Path(next(iter(spec.submodule_search_locations)))


def skipped(path: Path) -> bool:
    return any(fnmatch.fnmatch(str(path), glob) for glob in SKIP_GLOBS)


def module_name(root: Path, path: Path) -> tuple[str, bool]:
    parts = [root.name, *path.relative_to(root).with_suffix("").parts]
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False


def _absolute(module: _Module, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    base = module.name.split(".")
    keep = len(base) - node.level + (1 if module.is_package else 0)
    return ".".join([*base[:keep], *([node.module] if node.module else [])])


def _record_import(module: _Module, node: ast.Import | ast.ImportFrom) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            module.imports[local] = alias.name if alias.asname else local
        return
    source = _absolute(module, node)
    for alias in node.names:
        module.imports[alias.asname or alias.name] = f"{source}.{alias.name}"


def _assigned(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [
        named.id
        for target in targets
        for named in ast.walk(target)
        if isinstance(named, ast.Name)
    ]


def _read(root: Path, path: Path) -> _Module:
    name, is_package = module_name(root, path)
    module = _Module(
        name=name, path=path, is_package=is_package, tree=ast.parse(path.read_text())
    )
    for node in module.tree.body:
        match node:
            case ast.Import() | ast.ImportFrom():
                _record_import(module, node)
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                module.units[node.name] = node
            case ast.Assign() | ast.AnnAssign():
                for target in _assigned(node):
                    module.units[target] = node
            case _:
                module.loose.append(node)
    return module


@functools.cache
def modules() -> dict[str, _Module]:
    found: dict[str, _Module] = {}
    for package in PACKAGES:
        root = package_root(package)
        for path in sorted(root.rglob("*.py")):
            if not skipped(path):
                module = _read(root, path)
                found[module.name] = module
    return found


def resolve(qualname: str, depth: int = 0) -> str | None:
    held = modules()
    if qualname in held:
        return qualname
    owner, _, name = qualname.rpartition(".")
    module = held.get(owner)
    if module is None or depth > 8:
        return None
    if name in module.units:
        return qualname
    if name in module.imports:
        return resolve(module.imports[name], depth + 1)
    return None


def _dotted(node: ast.expr) -> list[str] | None:
    match node:
        case ast.Name(id=name):
            return [name]
        case ast.Attribute(value=value, attr=attr):
            head = _dotted(value)
            return None if head is None else [*head, attr]
        case _:
            return None


def _annotations(body: ast.AST) -> set[int]:
    held: list[ast.expr | None] = []
    for node in ast.walk(body):
        match node:
            case ast.arg(annotation=annotation):
                held.append(annotation)
            case (
                ast.FunctionDef(returns=returns) | ast.AsyncFunctionDef(returns=returns)
            ):
                held.append(returns)
            case ast.AnnAssign(annotation=annotation):
                held.append(annotation)
            case _:
                pass
    return {id(inner) for each in held if each is not None for inner in ast.walk(each)}


def _fields(body: ast.AST) -> set[int]:
    if not isinstance(body, ast.ClassDef):
        return set()
    return {
        id(inner)
        for statement in body.body
        if isinstance(statement, ast.AnnAssign)
        for inner in ast.walk(statement.annotation)
    }


def _references(module: _Module, body: ast.AST) -> set[str]:
    found: set[str] = set()
    typed = _annotations(body) - _fields(body)
    for node in ast.walk(body):
        if id(node) in typed:
            continue
        if not isinstance(node, ast.Name | ast.Attribute):
            continue
        chain = _dotted(node)
        if chain is None:
            continue
        head = chain[0]
        if head in module.units:
            found.add(f"{module.name}.{head}")
        elif head in module.imports:
            base = module.imports[head]
            found.update(
                ".".join([base, *chain[1:k]]) for k in range(1, len(chain) + 1)
            )
    return found


def _unit_of(qualname: str) -> tuple[_Module, str] | None:
    resolved = resolve(qualname)
    if resolved is None:
        return None
    held = modules()
    if resolved in held:
        return held[resolved], ""
    owner, _, name = resolved.rpartition(".")
    return held[owner], name


def references_of(qualname: str) -> set[str]:
    located = _unit_of(qualname)
    if located is None:
        return set()
    module, name = located
    body: list[ast.AST] = [module.units[name]] if name else list(module.loose)
    return {ref for part in body for ref in _references(module, part)}


def _called(module: _Module, call: ast.Call) -> str | None:
    chain = _dotted(call.func)
    if chain is None:
        return None
    head = chain[0]
    if head in module.units:
        return resolve(".".join([module.name, *chain]))
    if head in module.imports:
        return resolve(".".join([module.imports[head], *chain[1:]]))
    return None


def _calls() -> Iterator[tuple[str, ast.Call, _Module]]:
    for module in modules().values():
        for name, unit in module.units.items():
            for call in ast.walk(unit):
                if isinstance(call, ast.Call):
                    yield f"{module.name}.{name}", call, module


@functools.cache
def _writers() -> dict[str, frozenset[str]]:
    found: dict[str, set[str]] = {}
    for caller, call, module in _calls():
        if not caller.startswith(GRAPH_NODES):
            continue
        made = _called(module, call)
        if made is None or not made.startswith(STATE_MODELS):
            continue
        located = _unit_of(made)
        if located is not None and isinstance(
            located[0].units.get(located[1]), ast.ClassDef
        ):
            found.setdefault(made, set()).add(caller)
    return {made: frozenset(callers) for made, callers in found.items()}


@functools.cache
def _durable_bodies() -> dict[str, frozenset[str]]:
    found: dict[str, set[str]] = {}
    for _, call, module in _calls():
        if _called(module, call) != DURABLE_REGISTRATION or not call.args:
            continue
        declared = _dotted(call.args[0])
        if declared is None or declared[0] not in module.imports:
            continue
        declaration = resolve(module.imports[declared[0]])
        bodies = {
            resolved
            for argument in call.args[1:]
            for ref in _references(module, argument)
            if (resolved := resolve(ref)) is not None
        }
        if declaration is not None:
            found.setdefault(declaration, set()).update(bodies)
    return {declared: frozenset(bodies) for declared, bodies in found.items()}


def _onward(current: str) -> set[str]:
    return (
        references_of(current)
        | _writers().get(current, frozenset())
        | _durable_bodies().get(current, frozenset())
    )


def reach(roots: Iterable[str], fences: Iterable[str] = ()) -> set[str]:
    seen: set[str] = {f for f in (resolve(fence) for fence in fences) if f is not None}
    fenced = set(seen)
    queue = [r for r in (resolve(root) for root in roots) if r is not None]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        for ref in _onward(current):
            resolved = resolve(ref)
            if resolved is not None and resolved not in seen:
                queue.append(resolved)
    return seen - fenced


def _docstrings(tree: ast.AST) -> set[int]:
    return {
        id(owner.body[0].value)
        for owner in ast.walk(tree)
        if isinstance(
            owner, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        )
        and owner.body
        and isinstance(owner.body[0], ast.Expr)
        and isinstance(owner.body[0].value, ast.Constant)
    }


def _logged(tree: ast.AST) -> set[int]:
    return {
        id(inner)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _LOG_CALLS
        for argument in [*node.args, *(k.value for k in node.keywords)]
        for inner in ast.walk(argument)
    }


def _schema_descriptions(tree: ast.AST) -> set[int]:
    return {
        id(inner)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Field"
        for keyword in node.keywords
        if keyword.arg == "description"
        for inner in ast.walk(keyword.value)
    }


def _texts(node: ast.AST, skipped_ids: set[int]) -> Iterator[tuple[int, str]]:
    inside_fstrings = {
        id(part)
        for joined in ast.walk(node)
        if isinstance(joined, ast.JoinedStr)
        for part in ast.walk(joined)
        if part is not joined
    }
    for found in ast.walk(node):
        if id(found) in skipped_ids or id(found) in inside_fstrings:
            continue
        match found:
            case ast.Constant(value=str() as text):
                yield found.lineno, text
            case ast.JoinedStr(values=values):
                yield (
                    found.lineno,
                    "".join(
                        part.value
                        if isinstance(part, ast.Constant)
                        and isinstance(part.value, str)
                        else "{}"
                        for part in values
                    ),
                )


def _module_literals(module: _Module) -> Iterator[Literal]:
    ignored = (
        _docstrings(module.tree)
        | _logged(module.tree)
        | _schema_descriptions(module.tree)
    )
    owners: list[tuple[str, ast.AST]] = [
        (f"{module.name}.{name}", unit) for name, unit in module.units.items()
    ]
    owners.extend((module.name, stmt) for stmt in module.loose)
    seen: set[int] = set()
    for enclosing, unit in owners:
        if id(unit) in seen:
            continue
        seen.add(id(unit))
        for line, text in _texts(unit, ignored):
            if any(ch.isspace() for ch in text):
                yield Literal(module.path, line, enclosing, text)


@functools.cache
def all_literals() -> tuple[Literal, ...]:
    return tuple(
        literal for module in modules().values() for literal in _module_literals(module)
    )
