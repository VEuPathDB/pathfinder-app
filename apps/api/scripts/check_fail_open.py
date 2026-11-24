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
        case ast.Call(args=args, keywords=keywords):
            return any(_empty(arg) for arg in [*args, *(k.value for k in keywords)])
    return False


def _named_log(func: ast.expr) -> bool:
    match func:
        case ast.Attribute(attr=attr):
            return attr in _LOG_METHODS or "log" in attr.lower()
        case ast.Name(id=name):
            return "log" in name.lower()
    return False


def _logs(statement: ast.stmt) -> bool:
    match statement:
        case ast.Expr(value=ast.Call(func=func)):
            return _named_log(func)
    return False


def _quiet(statement: ast.stmt) -> bool:
    match statement:
        case ast.Expr(value=ast.Call()) | ast.Assign() | ast.AnnAssign() | ast.Pass():
            return True
    return False


def _exits(node: ast.AST) -> bool:
    match node:
        case ast.Raise() | ast.Return():
            return True
    return False


def _nodes(handler: ast.ExceptHandler) -> Iterator[ast.AST]:
    for statement in handler.body:
        yield from ast.walk(statement)


def _defaulted(handler: ast.ExceptHandler) -> ast.AST | None:
    for node in _nodes(handler):
        match node:
            case ast.Return(value=value) if _empty(value):
                return node
            case ast.Assign(value=value) if _empty(value):
                return node
            case ast.AnnAssign(value=value) if value is not None and _empty(value):
                return node
    return None


def _shape(handler: ast.ExceptHandler) -> tuple[str, str] | None:
    body = handler.body
    defaulted = _defaulted(handler)
    if defaulted is not None:
        return "returns or assigns an empty value", ast.unparse(defaulted)
    match body[-1]:
        case ast.Pass():
            return "ends in pass", "pass"
        case ast.Continue():
            return "ends in continue", "continue"
    if (
        not any(_exits(node) for node in _nodes(handler))
        and any(_logs(statement) for statement in body)
        and all(_quiet(statement) for statement in body)
    ):
        return "logs and falls through", "log"
    return None


def shape_of(handler: ast.ExceptHandler) -> str | None:
    found = _shape(handler)
    return None if found is None else found[0]


class _Scanner(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scope: list[str] = []
        self.seen: dict[str, int] = {}
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
        found = _shape(node)
        if found is not None:
            shape, default = found
            function = ".".join(self.scope) or "<module>"
            caught = "BaseException" if node.type is None else ast.unparse(node.type)
            identity = f"{self.path}:{function}:{caught}:{default}".replace(" ", "")
            repeat = self.seen.get(identity, 0) + 1
            self.seen[identity] = repeat
            key = identity if repeat == 1 else f"{identity}#{repeat}"
            self.found.append(Handler(key, node.lineno, shape))
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
