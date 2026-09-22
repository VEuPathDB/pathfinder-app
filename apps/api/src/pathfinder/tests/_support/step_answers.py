"""A stored thread with one pushed step, and a site that answers its genes.

The records are the shape toxodb answers for a transcript step read under
the representative-transcript view filter.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from assistant_core.persistence.models import Conversation
from veupathdb import JSONObject
from veupathdb.domain.strategy import StrategyAst
from veupathdb.wdk import WDKAnswer, WDKFilterValue

from pathfinder.persistence.models import ConversationStrategyView

SITE = "toxodb"
WDK_STRATEGY_ID = 900
PUSHED_STEP = "step_exons"
UNPUSHED_STEP = "step_go"
ROOT_STEP = "step_root"
WDK_STEP_ID = 11
GENE_TOTAL = 6414

ANSWER: JSONObject = {
    "records": [
        {
            "tables": {},
            "displayName": "TGME49_200010",
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "attributes": {
                "organism": "<i>Toxoplasma gondii ME49</i>",
                "gene_product": "dense granule protein GRA20",
                "primary_key": "TGME49_200010",
            },
            "id": [
                {"name": "gene_source_id", "value": "TGME49_200010"},
                {"name": "source_id", "value": "TGME49_200010.R447"},
                {"name": "project_id", "value": "ToxoDB"},
            ],
            "tableErrors": [],
        },
        {
            "tables": {},
            "displayName": "TGME49_200130",
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "attributes": {
                "organism": "<i>Toxoplasma gondii ME49</i>",
                "gene_product": "Toxoplasma gondii family C protein",
                "primary_key": "TGME49_200130",
            },
            "id": [
                {"name": "gene_source_id", "value": "TGME49_200130"},
                {"name": "source_id", "value": "TGME49_200130-t26_1"},
                {"name": "project_id", "value": "ToxoDB"},
            ],
            "tableErrors": [],
        },
    ],
    "meta": {
        "displayViewTotalCount": GENE_TOTAL,
        "tables": [],
        "pagination": {"offset": 0, "numRecords": 2},
        "viewTotalCount": GENE_TOTAL,
        "sorting": [],
        "recordClassName": "transcript",
        "responseCount": 2,
        "attributes": ["primary_key", "organism", "gene_product"],
        "totalCount": 6475,
        "displayTotalCount": GENE_TOTAL,
    },
}


def thread(
    *, record_type: str = "transcript"
) -> tuple[Conversation, ConversationStrategyView]:
    """A pushed strategy whose GO leaf has no WDK step yet."""
    now = datetime.now(UTC)
    ast = StrategyAst.model_validate(
        {
            "recordType": record_type,
            "root": {
                "id": ROOT_STEP,
                "searchName": "__transform__",
                "operator": "INTERSECT",
                "primaryInput": {"id": PUSHED_STEP, "searchName": "GenesByExonCount"},
                "secondaryInput": {"id": UNPUSHED_STEP, "searchName": "GenesByGoTerm"},
            },
            "wdkStepIds": {PUSHED_STEP: WDK_STEP_ID, ROOT_STEP: 12},
        }
    )
    conversation = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        assistant_id="pathfinder",
        site_id=SITE,
        name="multi-exon genes",
        created_at=now,
        updated_at=now,
    )
    strategy = ConversationStrategyView(
        wdk_strategy_id=WDK_STRATEGY_ID,
        wdk_strategy_created_here=True,
        is_saved=False,
        step_count=3,
        gene_set_auto_imported=False,
        imported_saved_strategy_ids=[],
        estimated_size=None,
        strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
    )
    return conversation, strategy


@dataclass(frozen=True)
class AnswerRead:
    """One answer read: the step, its columns, its page and its view."""

    step_id: int
    attributes: list[str] | None
    pagination: dict[str, int] | None
    view_filters: list[WDKFilterValue] | None


class SiteApi:
    """The strategy API surface the step records read touches."""

    def __init__(self, body: JSONObject = ANSWER) -> None:
        self.answer = WDKAnswer.model_validate(body)
        self.reads: list[AnswerRead] = []

    async def get_step_answer(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        self.reads.append(
            AnswerRead(
                step_id,
                attributes,
                pagination,
                None if view_filters is None else list(view_filters),
            )
        )
        return self.answer
