"""Check that Python source files stay under the line limit.

Enforces a 400-line cap (excluding blank lines and comments) on production and
test code. Devtools, cassettes and two declared pure-model files are exempt.

A baseline file ratchets the existing offenders: each entry records the count a
file had when it was baselined, and the file fails as soon as it grows past it.

Usage:
    python scripts/check_max_lines.py [--limit N] [--verbose]
    python scripts/check_max_lines.py --write-baseline
"""

import argparse
import sys
from pathlib import Path

DEFAULT_LIMIT = 400
DEFAULT_BASELINE = Path("src/pathfinder/tests/.max-lines-baseline.txt")
SRC_ROOTS = (Path("src/pathfinder"),)

# Directories and files exempt from the line limit.
EXEMPT_PATTERNS: set[str] = {
    "devtools/",
    "cassettes/",
    "__pycache__/",
    # Pure data-model files: splitting a schema module is artificial.
    "integrations/veupathdb/wdk_models.py",
    "persistence/models.py",
}


def _is_exempt(path: Path, root: Path) -> bool:
    rel = str(path.relative_to(root))
    return any(pattern in rel for pattern in EXEMPT_PATTERNS)


def _count_meaningful_lines(path: Path) -> int:
    """Count non-blank, non-comment lines."""
    count = 0
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def _scan(limit: int, *, verbose: bool) -> list[tuple[str, int]]:
    over: list[tuple[str, int]] = []
    for root in SRC_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if _is_exempt(path, root):
                continue
            lines = _count_meaningful_lines(path)
            if lines > limit:
                over.append((path.as_posix(), lines))
            elif verbose:
                print(f"  OK  {path} ({lines})")
    return over


def _load_baseline(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    entries: dict[str, int] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, _, count = stripped.rpartition("::")
        entries[name] = int(count)
    return entries


def _write_baseline(path: Path, over: list[tuple[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{name}::{lines}\n" for name, lines in sorted(over))
    path.write_text(
        "# Files over the meaningful-line cap when the cap reached tests.\n"
        "# Each line: <path>::<line count at baseline>. Shrink a file to trim\n"
        "# its entry; a file that grows past its count fails the check.\n" + body,
    )
    print(f"Wrote {len(over)} entries to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    over = _scan(args.limit, verbose=args.verbose)

    if args.write_baseline:
        _write_baseline(args.baseline, over)
        return 0

    baseline = _load_baseline(args.baseline)
    violations = [(n, c) for n, c in over if c > baseline.get(n, args.limit)]

    stale = sorted(set(baseline) - {n for n, _ in over})
    if stale:
        print(f"{len(stale)} baseline entry(ies) now under the cap; trim them:")
        for name in stale:
            print(f"  STALE  {name}")

    if violations:
        print(f"\n{len(violations)} file(s) exceed {args.limit} meaningful lines:\n")
        for name, lines in violations:
            allowed = baseline.get(name, args.limit)
            print(f"  FAIL  {name}: {lines} lines (allowed {allowed})")
        print("\nFix by splitting into smaller modules.")
        return 1

    print(
        f"All files under {args.limit} meaningful lines "
        f"({len(baseline)} baselined offender(s) ignored).",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
