from __future__ import annotations

import importlib
import os
import re
from pathlib import Path

from strategist.jobs import worker

_COMMAND = Path(__file__).resolve().parents[5] / "bin" / "strategist-worker"


def test_the_worker_command_is_an_executable_file() -> None:
    assert os.access(_COMMAND, os.X_OK)


def test_the_worker_command_starts_the_worker_module() -> None:
    (module,) = re.findall(r"-m ([\w.]+)", _COMMAND.read_text(encoding="utf8"))
    assert importlib.import_module(module) is worker


def test_the_image_ships_the_worker_command() -> None:
    dockerfile = (_COMMAND.parents[1] / "Dockerfile").read_text(encoding="utf8")
    assert "COPY apps/api/bin apps/api/bin" in dockerfile
