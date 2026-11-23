from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

TESTS = Path("src/strategist/tests")
DURATIONS = Path(".test_durations")
PATTERNS = ("test_*.py", "*_test.py")


def tier_files(tier: Path) -> list[str]:
    return sorted(
        {path.as_posix() for pattern in PATTERNS for path in tier.rglob(pattern)}
    )


def file_seconds(durations: dict[str, float]) -> dict[str, float]:
    summed: dict[str, float] = defaultdict(float)
    for node, seconds in durations.items():
        summed[node.split("::", 1)[0]] += seconds
    return dict(summed)


def split(
    files: Sequence[str], durations: dict[str, float], count: int
) -> list[list[str]]:
    known = file_seconds(durations)
    recorded = [known[name] for name in files if name in known]
    unrecorded = sum(recorded) / len(recorded) if recorded else 1.0
    weight = {name: known.get(name, unrecorded) for name in files}
    loads = [0.0] * count
    groups: list[list[str]] = [[] for _ in range(count)]
    for name in sorted(files, key=lambda name: (-weight[name], name)):
        lightest = min(range(count), key=lambda group: (loads[group], group))
        loads[lightest] += weight[name]
        groups[lightest].append(name)
    return [sorted(group) for group in groups]


def partition_errors(
    files: Sequence[str], groups: Sequence[Sequence[str]]
) -> list[str]:
    placed = [name for group in groups for name in group]
    errors = [
        f"{name} is in {placed.count(name)} groups"
        for name in sorted(set(placed))
        if placed.count(name) > 1
    ]
    errors += [f"{name} is in no group" for name in sorted(set(files) - set(placed))]
    errors += [
        f"{name} is not a test file" for name in sorted(set(placed) - set(files))
    ]
    errors += [
        f"group {index + 1} is empty" for index, group in enumerate(groups) if not group
    ]
    return errors


def _groups_of(tier: str, count: int) -> tuple[list[str], list[list[str]]]:
    files = tier_files(TESTS / tier)
    durations: dict[str, float] = json.loads(DURATIONS.read_text())
    return files, split(files, durations, count)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="split_tests")
    commands = parser.add_subparsers(dest="command", required=True)
    files_of = commands.add_parser("files")
    files_of.add_argument("tier")
    files_of.add_argument("count", type=int)
    files_of.add_argument("group", type=int)
    check = commands.add_parser("check")
    check.add_argument("tiers", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "files":
        _, groups = _groups_of(args.tier, args.count)
        print("\n".join(groups[args.group - 1]))
        return 0
    failed = False
    for tier_count in args.tiers:
        tier, count = tier_count.split(":")
        files, groups = _groups_of(tier, int(count))
        errors = partition_errors(files, groups)
        for error in errors:
            print(f"{tier}: {error}", file=sys.stderr)
        failed = failed or bool(errors)
        if not errors:
            print(
                f"{tier}: {len(files)} test files, each in exactly one of {count} groups"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
