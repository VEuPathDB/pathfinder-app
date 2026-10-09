from pathlib import Path

import pytest

from pathfinder.devtools import chat, evals
from pathfinder.devtools.chat import SitesChoiceError, chosen_sites_file
from pathfinder.evals.summary import EvalRunSummary
from pathfinder.platform.config import get_settings
from pathfinder.platform.stage_sites import SITES_CONFIG_VARIABLE, qa_sites_file

pytestmark = pytest.mark.usefixtures("restored_sites_file")


@pytest.fixture
def unnamed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SITES_CONFIG_VARIABLE, raising=False)


@pytest.mark.usefixtures("unnamed")
def test_a_turn_with_no_file_named_reads_the_qa_sites() -> None:
    assert chosen_sites_file(None, via_worker=False) == qa_sites_file()


def test_the_environment_names_the_file_when_the_flag_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SITES_CONFIG_VARIABLE, "/stack/sites.yaml")

    assert chosen_sites_file(None, via_worker=False) == Path("/stack/sites.yaml")
    assert chosen_sites_file("/x.yaml", via_worker=False) == Path("/x.yaml")


@pytest.mark.usefixtures("unnamed")
def test_a_worker_run_on_the_client_sites_is_refused() -> None:
    with pytest.raises(SitesChoiceError, match="the client's bundled sites file"):
        chosen_sites_file(None, via_worker=True)


def test_a_worker_run_on_another_file_than_the_worker_reads_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SITES_CONFIG_VARIABLE, "/stack/sites.yaml")

    assert chosen_sites_file(None, via_worker=True) == Path("/stack/sites.yaml")
    with pytest.raises(SitesChoiceError, match=r"/stack/sites\.yaml"):
        chosen_sites_file("/x.yaml", via_worker=True)


@pytest.mark.usefixtures("unnamed")
def test_a_debugger_turn_runs_on_the_file_it_chose(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[str | None] = []

    async def run_once(args: chat.RunArgs) -> int:
        del args
        seen.append(get_settings().veupathdb_sites_config)
        return 0

    monkeypatch.setattr(chat, "run_once", run_once)
    monkeypatch.setattr(
        "sys.argv",
        ["chat", "run", "hi", "--site", "plasmodb", "--run-dir", str(tmp_path)],
    )

    with pytest.raises(SystemExit) as exited:
        chat.main()

    assert exited.value.code == 0
    assert seen == [str(qa_sites_file())]


@pytest.mark.usefixtures("unnamed")
def test_a_debugger_worker_run_on_the_client_sites_exits_before_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "chat",
            "run",
            "hi",
            "--site",
            "plasmodb",
            "--run-dir",
            str(tmp_path),
            "--via-worker",
        ],
    )

    with pytest.raises(SystemExit) as exited:
        chat.main()

    assert exited.value.code == 2


def test_an_eval_run_must_name_its_sites_file() -> None:
    with pytest.raises(SystemExit):
        evals._build_parser().parse_args(["run"])


def test_an_eval_run_reads_the_file_it_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    named = tmp_path / "sites.yaml"
    named.write_text(qa_sites_file().read_text())
    seen: list[str | None] = []

    async def run_corpus(**options: object) -> EvalRunSummary:
        del options
        seen.append(get_settings().veupathdb_sites_config)
        return EvalRunSummary(
            harness="pydantic-evals",
            provider="mock",
            assistant_id="pathfinder",
            ran_at="2026-10-09T00:00:00+00:00",
            cases=[],
        )

    monkeypatch.setattr(evals, "run_corpus", run_corpus)

    assert evals.main(["run", "--sites", str(named)]) == 0
    assert seen == [str(named)]
