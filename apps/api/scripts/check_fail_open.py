import ast
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PACKAGE = Path("src/strategist")
ROOTS = ("ai", "services", "domain")
ALLOWLIST = Path("scripts/fail-open-allowed.txt")
_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical"})
_EMPTY_CALLS = frozenset({"set", "list", "dict", "tuple", "frozenset"})


@dataclass(frozen=True)
class Handler:
    key: str
    line: int
    shape: str


def _empty(node: ast.expr | None) -> bool:
    match node:
        case None | ast.List(elts=[]) | ast.Tuple(elts=[]) | ast.Set(elts=[]):
            return True
        case ast.Dict(keys=[]):
            return True
        case ast.Constant(value=value):
            return value in (None, False, 0, "") and value is not True
        case ast.Call(func=ast.Name(id=name), args=[], keywords=[]):
            return name in _EMPTY_CALLS
        case ast.Call(args=args):
            return any(_empty(arg) for arg in args)
    return False


def _logs(statement: ast.stmt) -> bool:
    match statement:
        case ast.Expr(value=ast.Call(func=ast.Attribute(attr=attr))):
            return attr in _LOG_METHODS
    return False


def _returns_empty(statement: ast.stmt) -> bool:
    match statement:
        case ast.Return(value=value):
            return _empty(value)
        case ast.Assign(value=value) | ast.AnnAssign(value=value):
            return value is not None and _empty(value)
    return False


def shape_of(handler: ast.ExceptHandler) -> str | None:
    body = handler.body
    if any(_returns_empty(statement) for statement in body):
        return "returns or assigns an empty value"
    match body[-1]:
        case ast.Pass():
            return "ends in pass"
        case ast.Continue():
            return "ends in continue"
    if all(_logs(statement) for statement in body):
        return "only logs"
    return None


class _Scanner(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scope: list[str] = []
        self.counts: dict[str, int] = {}
        self.found: list[Handler] = []

    def _enter(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = _enter
    visit_AsyncFunctionDef = _enter
    visit_ClassDef = _enter

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        shape = shape_of(node)
        if shape is not None:
            function = ".".join(self.scope) or "<module>"
            ordinal = self.counts.get(function, 0) + 1
            self.counts[function] = ordinal
            self.found.append(
                Handler(f"{self.path}:{function}:{ordinal}", node.lineno, shape)
            )
        self.generic_visit(node)


def scan_source(source: str, path: str) -> list[Handler]:
    scanner = _Scanner(path)
    scanner.visit(ast.parse(source))
    return scanner.found


def scan_tree(package: Path) -> Iterator[Handler]:
    for root in ROOTS:
        for file in sorted((package / root).rglob("*.py")):
            yield from scan_source(
                file.read_text(), file.relative_to(package).as_posix()
            )


def read_allowlist(text: str) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, reason = line.partition(" ")
        if not reason.strip():
            msg = f"{key}: an allowlisted handler states its reason"
            raise ValueError(msg)
        allowed[key] = reason.strip()
    return allowed


def violations(found: list[Handler], allowed: dict[str, str]) -> list[str]:
    keys = {handler.key for handler in found}
    return [
        *(f"{h.key} (line {h.line}): {h.shape}" for h in found if h.key not in allowed),
        *(
            f"{key}: allowlisted, but no such handler"
            for key in allowed
            if key not in keys
        ),
    ]


def main() -> int:
    found = list(scan_tree(PACKAGE))
    failures = violations(found, read_allowlist(ALLOWLIST.read_text()))
    if not failures:
        print(f"fail-open: {len(found)} handler(s), each allowlisted with its reason.")
        return 0
    print(f"{len(failures)} handler(s) turn a failure into an ordinary value:\n")
    for failure in failures:
        print(f"  {failure}")
    print(
        "\nRaise, return a typed unknown (Unread, an unchecked SiteCheck), or list "
        f"the handler in {ALLOWLIST} with the test that shows its result is correct."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
