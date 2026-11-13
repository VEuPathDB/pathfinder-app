"""Flag tests whose only assertions are weak.

A "weak" assertion survives almost any mutation to the function under test:
- ``assert x``                       (truthy)
- ``assert x is not None``           (non-null)
- ``assert isinstance(x, T)``        (type only)
- ``assert hasattr(x, "...")``
- ``assert "key" in obj``            (membership without value check)
- ``assert len(x)`` / ``assert len(x) > 0`` via Call-only

A test that contains ONLY weak assertions, OR no assertions at all, fails
this check. ``pytest.raises(...)``, ``response.raise_for_status()``,
``Model.model_validate(...)``, and any equality / ordering / regex compare
count as strong evidence of a real behavioral check.

Usage:
    uv run python scripts/check_weak_assertions.py
    uv run python scripts/check_weak_assertions.py --baseline tests/.weak-baseline.txt

The baseline file lets us ratchet: existing offenders are listed there and
ignored; only NEW offenders fail the build. Trim the baseline as tests get
fixed.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

SRC_ROOT = Path("src/strategist/tests")
SKIP_NAMES = {"__init__.py", "conftest.py"}

# Single-callable predicates that we treat as weak when used bare (no comparison).
_WEAK_BUILTINS = {"isinstance", "hasattr", "callable", "len", "bool", "any", "all"}

# Calls that, when executed, raise on bad data — counts as strong.
_STRONG_VALIDATING_CALLS = {
    "raise_for_status",
    "model_validate",
    "model_validate_json",
    "model_validate_strings",
}


class _AssertWalker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.weak = 0
        self.strong = 0
        self.has_pytest_raises = False
        self.has_validating_call = False

    def visit_Assert(self, node: ast.Assert) -> None:
        if _is_weak_assert(node.test):
            self.weak += 1
        else:
            self.strong += 1
        # Don't recurse into the assert expression.

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if _is_pytest_raises(item.context_expr):
                self.has_pytest_raises = True
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            if _is_pytest_raises(item.context_expr):
                self.has_pytest_raises = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in _STRONG_VALIDATING_CALLS
        ):
            self.has_validating_call = True
        self.generic_visit(node)


def _is_pytest_raises(expr: ast.expr) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    if isinstance(func, ast.Attribute) and func.attr == "raises":
        return True
    return isinstance(func, ast.Name) and func.id == "raises"


def _is_weak_compare(expr: ast.Compare) -> bool:
    if len(expr.ops) != 1:
        return False
    op = expr.ops[0]
    if isinstance(op, (ast.Is, ast.IsNot)):
        return _compares_to_none(expr)
    if isinstance(op, (ast.In, ast.NotIn)):
        return _is_weak_membership(expr)
    return False


def _is_weak_assert(expr: ast.expr) -> bool:
    if isinstance(expr, (ast.Constant, ast.Name, ast.Attribute, ast.Subscript)):
        return True
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return _is_weak_assert(expr.operand)
    if isinstance(expr, ast.BoolOp):
        return all(_is_weak_assert(v) for v in expr.values)
    if isinstance(expr, ast.Call):
        return isinstance(expr.func, ast.Name) and expr.func.id in _WEAK_BUILTINS
    if isinstance(expr, ast.Compare):
        return _is_weak_compare(expr)
    return False


def _is_weak_membership(expr: ast.Compare) -> bool:
    """`In`/`NotIn` is strong when EITHER side is a literal — a Constant,
    a Set/List/Tuple/Dict of Constants, or an attribute path on such a
    container. Two dynamic Names is the weak case (`key in dict`).
    """
    left = expr.left
    right = expr.comparators[0]
    return not (_is_literal_or_collection(left) or _is_literal_or_collection(right))


def _is_literal_or_collection(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return all(isinstance(e, ast.Constant) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(isinstance(e, ast.Constant) for e in node.keys if e is not None)
    return False


def _compares_to_none(expr: ast.Compare) -> bool:
    return (
        len(expr.comparators) == 1
        and isinstance(expr.comparators[0], ast.Constant)
        and expr.comparators[0].value is None
    )


def _scan_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[_AssertWalker, bool]:
    walker = _AssertWalker()
    walker.visit(fn)
    has_strong = (
        walker.strong > 0 or walker.has_pytest_raises or walker.has_validating_call
    )
    return walker, has_strong


def _classify(walker: _AssertWalker, *, has_strong: bool) -> str | None:
    if (
        walker.weak == 0
        and walker.strong == 0
        and not (walker.has_pytest_raises or walker.has_validating_call)
    ):
        return "no_assertions"
    if not has_strong:
        return "only_weak_assertions"
    return None


def _scan_file(path: Path) -> list[tuple[Path, int, str, str]]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return []
    offenders: list[tuple[Path, int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        walker, has_strong = _scan_function(node)
        verdict = _classify(walker, has_strong=has_strong)
        if verdict:
            offenders.append((path, node.lineno, node.name, verdict))
    return offenders


def _load_baseline(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


def _key(path: Path, fn_name: str) -> str:
    return f"{path.as_posix()}::{fn_name}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Specific test files / directories to scan (default: all tests).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("src/strategist/tests/.weak-baseline.txt"),
        help="File listing 'path::fn_name' offenders to ignore.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Overwrite the baseline file with the current set of offenders.",
    )
    args = parser.parse_args()

    targets = args.paths or [SRC_ROOT]
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            files.append(target)
        else:
            files.extend(
                p for p in target.rglob("test_*.py") if p.name not in SKIP_NAMES
            )

    all_offenders: list[tuple[Path, int, str, str]] = []
    for path in sorted(files):
        all_offenders.extend(_scan_file(path))

    if args.write_baseline:
        keys = sorted({_key(p, fn) for p, _, fn, _ in all_offenders})
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            "# Existing weak-assertion offenders; trim as tests get fixed.\n"
            "# Each line: <relative_path>::<test_function_name>\n"
            + "\n".join(keys)
            + ("\n" if keys else ""),
        )
        print(f"Wrote {len(keys)} entries to {args.baseline}")
        return 0

    baseline = _load_baseline(args.baseline)
    new_offenders = [o for o in all_offenders if _key(o[0], o[2]) not in baseline]

    if new_offenders:
        print(f"\n{len(new_offenders)} test(s) with weak-only or missing assertions:\n")
        for path, lineno, name, reason in new_offenders:
            print(f"  {path}:{lineno}  {name}  [{reason}]")
        print(
            "\nFix by replacing truthy / non-null / type / membership-only "
            "assertions with structural value checks (== exact, == [list], "
            "pytest.raises(SpecificError), Model.model_validate(...))."
        )
        if baseline:
            print(
                f"\nBaseline at {args.baseline} suppresses "
                f"{len(baseline)} pre-existing offender(s)."
            )
        return 1

    total_tests = sum(1 for _ in _iter_test_functions(files))
    suppressed = len(baseline) if baseline else 0
    print(
        f"weak-assertion check passed: {total_tests} tests scanned, "
        f"{suppressed} pre-existing offender(s) ignored via baseline."
    )
    return 0


def _iter_test_functions(files: list[Path]):
    for path in files:
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name.startswith("test_"):
                yield path, node


if __name__ == "__main__":
    sys.exit(main())
