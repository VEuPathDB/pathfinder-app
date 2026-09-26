"""The corpus on disk: one JSON file per case, named by the case.

Each file carries its own provenance as data. A case arrives promoted by the
curation step, or written by hand from a cataloged failure or a UAT flow.
"""

from __future__ import annotations

from pathlib import Path

from pathfinder.evals.case import EvalCase

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
ATTACHMENTS_DIR = CORPUS_DIR / "files"


def _directory(directory: Path | None) -> Path:
    return CORPUS_DIR if directory is None else directory


def case_names(*, directory: Path | None = None) -> list[str]:
    """The names of the cases on disk, sorted."""
    root = _directory(directory)
    if not root.is_dir():
        return []
    return sorted(path.stem for path in root.glob("*.json"))


def load_case(name: str, *, directory: Path | None = None) -> EvalCase:
    """Read one case, or fail naming the command that adds one."""
    path = _directory(directory) / f"{name}.json"
    if not path.is_file():
        msg = (
            f"{path} is missing; promote a staged candidate with "
            f"`python -m pathfinder.devtools.evals promote <staging-id> --name {name}`"
        )
        raise FileNotFoundError(msg)
    return EvalCase.model_validate_json(path.read_text())


def load_corpus(*, directory: Path | None = None) -> list[EvalCase]:
    """Every case on disk, in name order."""
    root = _directory(directory)
    return [load_case(name, directory=root) for name in case_names(directory=root)]


def attachment_paths(case: EvalCase, turn: int) -> list[Path]:
    """The files *case* attaches to the turn at index *turn*, in order."""
    return [ATTACHMENTS_DIR / name for name in case.attachments.get(turn, [])]


def write_case(case: EvalCase, *, directory: Path | None = None) -> Path:
    """Add one case to the corpus. An existing name is refused, never replaced."""
    case.assert_de_identified()
    root = _directory(directory)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{case.name}.json"
    if path.exists():
        msg = f"{case.name} is already in the corpus at {path}; choose another name"
        raise FileExistsError(msg)
    path.write_text(case.model_dump_json(indent=2, by_alias=True) + "\n")
    return path


__all__ = [
    "ATTACHMENTS_DIR",
    "CORPUS_DIR",
    "attachment_paths",
    "case_names",
    "load_case",
    "load_corpus",
    "write_case",
]
