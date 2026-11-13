from pathlib import Path

import pytest
from veupathdb.testing import NEEDS_QA_RECORDING
from veupathdb.testing.eda_fixtures import FIXTURE_DIR as CLIENT_EDA_STORE
from veupathdb.testing.wdk_fixtures import (
    RecordedWDKResponse,
    fixture_request,
    load_recorded,
)

SUITE_WDK_STORE = Path(__file__).resolve().parents[1] / "fixtures" / "wdk"


def _recorded(store: Path) -> bool:
    return store.is_dir() and any(store.glob("*.json"))


def needs_qa_recordings(*stores: Path) -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not all(_recorded(store) for store in stores), reason=NEEDS_QA_RECORDING
    )


needs_suite_recordings = needs_qa_recordings(SUITE_WDK_STORE)
needs_client_eda_recordings = needs_qa_recordings(CLIENT_EDA_STORE)


def qa_recording(path: Path) -> Path:
    if not path.is_file():
        pytest.skip(NEEDS_QA_RECORDING, allow_module_level=True)
    return path


def client_recording(name: str) -> RecordedWDKResponse:
    qa_recording(fixture_request(name).file)
    return load_recorded(name)
