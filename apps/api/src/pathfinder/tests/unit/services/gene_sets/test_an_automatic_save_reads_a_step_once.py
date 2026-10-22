"""An automatic save reads its step's count first, and reads the answer once
within the cap, or not at all above it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from veupathdb.errors import DataParsingError
from veupathdb.wdk import (
    StrategyAPI,
    WDKAnswer,
    WDKFilterValue,
    WDKStep,
    WDKStrategyDetails,
)

from pathfinder.domain.gene_homes import GeneHome
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.gene_sets import homes, strategy_genes
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.step_genes import (
    IncompleteAnswerError,
    TooManyGenesError,
)
from pathfinder.services.gene_sets.strategy_genes import RecordsAreNotGenesError
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies import auto_import
from pathfinder.services.strategies.auto_import import auto_import_gene_set
from pathfinder.tests._support.gene_set_store import InMemoryGeneSetStore
from pathfinder.tests._support.logs import logged_events

STRATEGY_ID = 214645070
GROUP_STEP_ID = 227284180
ROOT_STEP_ID = 227284190
SINGLETON_PROTEINS = 523_795
CAP = get_settings().step_genes_cap

Row = tuple[str, dict[str, str]]


def _protein(n: int) -> Row:
    gene = f"PF3D7_{n:07d}"
    return (
        f"{gene}.1-p1",
        {
            "gene_source_id": gene,
            "gene_source_url": f"https://qa.plasmodb.org/plasmo.qa/app/record/gene/{gene}",
        },
    )


_PROTEINS: list[Row] = [
    _protein(103400),
    (
        "TGME49_200010-t26_1-p1",
        {
            "gene_source_id": "TGME49_200010",
            "gene_source_url": "https://qa.toxodb.org/toxo.qa/app/record/gene/TGME49_200010",
        },
    ),
]

Read = tuple[list[str] | None, dict[str, int] | None, list[WDKFilterValue] | None]


def _step(step_id: int, search: str, record_class: str, size: int) -> dict[str, object]:
    return {
        "id": step_id,
        "searchName": search,
        "searchConfig": {"parameters": {}},
        "recordClassName": record_class,
        "estimatedSize": size,
    }


@dataclass
class _Site(StrategyAPI):
    root_size: int
    rows: list[Row] = field(default_factory=lambda: list(_PROTEINS))
    total: int | None = None
    root_class: str = "sequence"
    reads: list[Read] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    steps_read: list[int] = field(default_factory=list)

    def _steps(self) -> dict[str, dict[str, object]]:
        return {
            str(GROUP_STEP_ID): _step(
                GROUP_STEP_ID, "GroupsBySequenceCount", "group", SINGLETON_PROTEINS
            ),
            str(ROOT_STEP_ID): _step(
                ROOT_STEP_ID, "FromGroups", self.root_class, self.root_size
            ),
        }

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": strategy_id,
                "name": "Organisms With Most OrthoMCL Singletons",
                "rootStepId": ROOT_STEP_ID,
                "recordClassName": self.root_class,
                "estimatedSize": -1,
                "stepTree": {
                    "stepId": ROOT_STEP_ID,
                    "primaryInput": {"stepId": GROUP_STEP_ID},
                },
                "steps": self._steps(),
            }
        )

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        self.steps_read.append(step_id)
        return WDKStep.model_validate(self._steps()[str(step_id)])

    async def get_step_count(self, step_id: int, user_id: str | None = None) -> int:
        del user_id
        self.counts.append(step_id)
        return self.root_size

    async def get_step_answer(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        del step_id
        self.reads.append(
            (
                attributes,
                pagination,
                None if view_filters is None else list(view_filters),
            )
        )
        wanted = (pagination or {}).get("numRecords", -1)
        page = self.rows if wanted < 0 else self.rows[:wanted]
        total = len(self.rows) if self.total is None else self.total
        return WDKAnswer.model_validate(
            {
                "meta": {
                    "totalCount": total,
                    "displayViewTotalCount": total,
                    "responseCount": len(page),
                    "recordClassName": self.root_class,
                },
                "records": [
                    {"id": [{"name": "source_id", "value": key}], "attributes": attrs}
                    for key, attrs in page
                ],
            }
        )


def _serve(monkeypatch: pytest.MonkeyPatch, site: _Site) -> _Site:
    monkeypatch.setattr(homes, "get_strategy_api", lambda _site_id: site)
    monkeypatch.setattr(strategy_genes, "get_strategy_api", lambda _site_id: site)
    return site


class _Store(InMemoryGeneSetStore):
    async def find_strategy_import(
        self, user_id: UUID, wdk_strategy_id: int
    ) -> GeneSet | None:
        del user_id, wdk_strategy_id
        return None


@dataclass
class _Repo:
    updates: list[tuple[UUID, ConversationUpdate]] = field(default_factory=list)

    async def update_conversation(
        self, conversation_id: UUID, upd: ConversationUpdate, /
    ) -> None:
        self.updates.append((conversation_id, upd))

    async def name_and_link(self, conversation_id: UUID, gene_set: GeneSet, /) -> None:
        await self.update_conversation(
            conversation_id,
            ConversationUpdate(
                gene_set_id=gene_set.id,
                gene_set_id_set=True,
                gene_set_auto_imported=True,
            ),
        )


def _thread(
    record_type: str | None = "sequence",
) -> tuple[Conversation, ConversationStrategyView]:
    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        site_id="orthomcl",
        name="Organisms With Most OrthoMCL Singletons",
        created_at=now,
        updated_at=now,
    )
    strategy = ConversationStrategyView(
        wdk_strategy_id=STRATEGY_ID, record_type=record_type, step_count=2
    )
    return conversation, strategy


async def _auto_import(
    store: _Store, record_type: str | None = "sequence"
) -> tuple[GeneSet | None, _Repo]:
    thread = _thread(record_type)
    repo = _Repo()
    created = await auto_import_gene_set(
        thread,
        name="Organisms With Most OrthoMCL Singletons",
        conv_repo=repo,
        gene_set_service=GeneSetService(store),
        site_id="orthomcl",
        user_id=thread[0].user_id,
    )
    return created, repo


_HOME_READ = ["primary_key", "gene_source_id", "gene_source_url"]


async def test_a_build_above_the_cap_sends_no_answer_read_and_skips(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    site = _serve(monkeypatch, _Site(root_size=SINGLETON_PROTEINS))
    store = _Store()

    created, repo = await _auto_import(store)

    assert (created, site.reads, site.counts, store.rows, repo.updates) == (
        None,
        [],
        [],
        {},
        [],
    )
    assert logged_events(caplog.records, logger=auto_import.__name__) == [
        "Skipped gene set auto-import"
    ]


async def test_a_step_above_the_cap_is_refused_with_its_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, _Site(root_size=SINGLETON_PROTEINS))

    with pytest.raises(TooManyGenesError) as caught:
        await GeneSetService(_Store()).create_from_strategy(
            user_id=uuid4(),
            name="singletons",
            site_id="orthomcl",
            wdk_strategy_id=STRATEGY_ID,
            record_type="sequence",
        )

    assert (caught.value.count, caught.value.cap, site.reads) == (
        SINGLETON_PROTEINS,
        CAP,
        [],
    )
    assert f"{SINGLETON_PROTEINS:,}" in str(caught.value.detail)


async def test_a_step_of_exactly_the_cap_is_read_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [_protein(n) for n in range(CAP)]
    site = _serve(monkeypatch, _Site(root_size=CAP, rows=rows))

    found = await homes.read_step_genes("orthomcl", ROOT_STEP_ID)

    assert site.reads == [(_HOME_READ, {"offset": 0, "numRecords": CAP}, None)]
    assert (len(found.gene_ids), len(found.homes)) == (CAP, CAP)


async def test_a_step_one_above_the_cap_is_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, _Site(root_size=CAP + 1))

    with pytest.raises(TooManyGenesError):
        await homes.read_step_genes("orthomcl", ROOT_STEP_ID)

    assert site.reads == []


async def test_an_empty_step_is_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    site = _serve(monkeypatch, _Site(root_size=0, rows=[]))

    found = await homes.read_step_genes("orthomcl", ROOT_STEP_ID)

    assert (found.gene_ids, found.homes, site.reads) == ([], {}, [])


async def test_a_small_build_is_read_once_from_the_strategy_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, _Site(root_size=len(_PROTEINS)))
    store = _Store()

    created, repo = await _auto_import(store)

    assert created is not None
    assert site.reads == [(_HOME_READ, {"offset": 0, "numRecords": CAP}, None)]
    assert (site.steps_read, site.counts) == ([], [])
    [saved] = store.rows.values()
    assert saved.gene_ids == ["PF3D7_0103400.1-p1", "TGME49_200010-t26_1-p1"]
    assert saved.homes == {
        "PF3D7_0103400.1-p1": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb"),
        "TGME49_200010-t26_1-p1": GeneHome(gene_id="TGME49_200010", site_id="toxodb"),
    }
    assert (saved.wdk_step_id, saved.step_count, len(repo.updates)) == (
        ROOT_STEP_ID,
        2,
        1,
    )


async def test_an_answer_that_grew_past_its_size_is_read_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [_protein(n) for n in range(3)]
    _serve(monkeypatch, _Site(root_size=2, rows=rows))

    found = await homes.read_step_genes("orthomcl", ROOT_STEP_ID)

    assert found.gene_ids == [key for key, _ in rows]


async def test_an_answer_that_grew_past_the_cap_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _Site(root_size=2, total=CAP + 1))

    with pytest.raises(TooManyGenesError) as caught:
        await homes.read_step_genes("orthomcl", ROOT_STEP_ID)

    assert caught.value.count == CAP + 1


async def test_an_answer_that_sends_fewer_rows_than_it_counts_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _Site(root_size=2, total=3))

    with pytest.raises(IncompleteAnswerError) as caught:
        await homes.read_step_genes("orthomcl", ROOT_STEP_ID)

    assert (caught.value.counted, caught.value.returned) == (3, 2)


async def test_a_transcript_step_is_read_one_row_per_gene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(
        monkeypatch,
        _Site(
            root_size=1,
            rows=[("PF3D7_0103400", {})],
            root_class="transcript",
        ),
    )

    found = await homes.read_step_genes("plasmodb", ROOT_STEP_ID)

    assert site.reads == [
        (
            ["primary_key"],
            {"offset": 0, "numRecords": CAP},
            [WDKFilterValue(name="representativeTranscriptOnly", value={})],
        )
    ]
    assert (found.gene_ids, found.record_class) == (["PF3D7_0103400"], "transcript")


async def test_a_step_without_a_size_is_counted_before_it_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site(root_size=SINGLETON_PROTEINS)

    async def _unsized(step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep.model_validate(
            {**site._steps()[str(step_id)], "estimatedSize": None}
        )

    monkeypatch.setattr(site, "find_step", _unsized)
    _serve(monkeypatch, site)

    with pytest.raises(TooManyGenesError):
        await homes.read_step_genes("orthomcl", ROOT_STEP_ID)

    assert (site.counts, site.reads) == ([ROOT_STEP_ID], [])


async def test_a_strategy_of_groups_is_not_saved_and_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, _Site(root_size=2, root_class="group"))
    store = _Store()

    created, _repo = await _auto_import(store, record_type=None)

    assert (created, site.reads, store.rows) == (None, [], {})


async def test_a_resync_onto_groups_names_the_record_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, _Site(root_size=2, root_class="group"))
    store = _Store()
    await store.save(
        GeneSet(
            id="g1",
            name="singletons",
            site_id="orthomcl",
            gene_ids=["PF3D7_0103400.1-p1"],
            source="strategy",
            wdk_strategy_id=STRATEGY_ID,
        )
    )

    with pytest.raises(RecordsAreNotGenesError) as caught:
        await GeneSetService(store).resync_strategy(
            "g1",
            wdk_strategy_id=STRATEGY_ID,
            site_id="orthomcl",
            answer_revision="9f1c2b7a4e3d5c60",
        )

    assert "group" in str(caught.value.detail)
    assert site.reads == []


async def test_a_strategy_that_omits_its_root_is_refused_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, _Site(root_size=len(_PROTEINS)))
    whole = await site.get_strategy(STRATEGY_ID)
    rootless = whole.model_copy(
        update={"steps": {str(GROUP_STEP_ID): whole.steps[str(GROUP_STEP_ID)]}}
    )
    monkeypatch.setattr(site, "get_strategy", AsyncMock(return_value=rootless))

    with pytest.raises(DataParsingError):
        await strategy_genes.read_strategy_genes(
            "orthomcl", STRATEGY_ID, record_type="sequence"
        )

    assert site.reads == []
