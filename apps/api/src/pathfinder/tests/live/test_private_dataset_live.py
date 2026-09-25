"""A researcher's installed RNA-Seq upload opens, runs DESeq2 and exports the site's count.

The check uses the heat shock upload this lane makes, when the account already
holds it installed on PlasmoDB. Otherwise it uploads the counts of the curated
heat shock study, waits for the install, and deletes the upload when it ends.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.progress import TaskProgressEmitter
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import get_eda_analyses_client, get_eda_client
from veupathdb.testing import DriftLog
from veupathdb.wdk import (
    RNASEQRC,
    RnaSeqCountFile,
    RnaSeqRcUpload,
    VdiDatasetGoneError,
    VdiDatasetPostMeta,
    VdiInstallDisposition,
    get_strategy_api,
    get_vdi_client,
    poll_interval_seconds,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.jobs.auth_context import attach_application
from pathfinder.jobs.impls.eda_compute_impl import run_eda_compute_impl
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.eda.authoring import resolve_eda_user_id
from pathfinder.services.eda.catalog import get_study_detail_for_dataset
from pathfinder.services.eda.description import describe_study, permission_facts
from pathfinder.tests._support.database import no_database
from pathfinder.tests.integration.http.conftest import client_for, make_user

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"
_PROJECT = "PlasmoDB"
# The curated heat shock study whose counts a new upload carries.
_STUDY = "STUDY_e973eadd57"
_SAMPLES = "ENT_8151325d"
_COUNTS = "ENT_fd574cd6"
# Condition, strain, genotype, temperature: every sample column but its label.
_SAMPLE_VARIABLES = ("VAR_081ab087", "VAR_26d10fbf", "VAR_84f17484", "VAR_7033e90f")
_SAMPLE_HEADER = "sample\ttemperature_condition\tstrain\tgenotype\ttemperature_celsius"
_GROUP_A, _GROUP_B = "wildtype", "delta-DHC mutant"
# The name this lane uploads the heat shock counts under.
_UPLOAD_NAME = "PathFinder live test counts"
_INSTALL_BUDGET_SECONDS = 40 * 60
_COMPUTE_BUDGET_SECONDS = 10 * 60


@dataclass
class _Upload:
    dataset_id: str
    vdi_id: str
    created_here: bool
    install_seconds: float | None = None


async def _installed(client: httpx.AsyncClient) -> tuple[str, str] | None:
    """The dataset id and the VDI id of this lane's heat shock upload, once readable."""
    listed = await client.get(f"/api/v1/eda/datasets?siteId={_SITE}")
    assert listed.status_code == 200, listed.text
    ready = [
        (str(row["datasetId"]), str(row["vdiId"]))
        for row in listed.json()["datasets"]
        if row["datasetId"] is not None and row["name"] == _UPLOAD_NAME
    ]
    return ready[0] if ready else None


async def _curated_counts() -> tuple[str, bytes, bytes]:
    """The curated study's samples and counts, as one sample table and two matrices."""
    eda = get_eda_client(_SITE)
    samples: Any = await eda.request_json(
        "POST",
        f"/studies/{_STUDY}/entities/{_SAMPLES}/tabular",
        json={"filters": [], "outputVariableIds": list(_SAMPLE_VARIABLES)},
    )
    counts: Any = await eda.request_json(
        "POST",
        f"/studies/{_STUDY}/entities/{_COUNTS}/tabular",
        json={
            "filters": [],
            "outputVariableIds": [
                "VEUPATHDB_GENE_ID",
                "SEQUENCE_READ_COUNT_SENSE",
                "SEQUENCE_READ_COUNT_ANTISENSE",
            ],
        },
    )
    names = [row[0] for row in samples[1:]]
    details = "\n".join([_SAMPLE_HEADER, *("\t".join(row) for row in samples[1:])])
    sense: dict[str, dict[str, str]] = {}
    antisense: dict[str, dict[str, str]] = {}
    for _row_id, sample, gene, sense_count, antisense_count in counts[1:]:
        sense.setdefault(gene, {})[sample] = sense_count
        antisense.setdefault(gene, {})[sample] = antisense_count

    def matrix(table: dict[str, dict[str, str]]) -> bytes:
        lines = ["gene_id\t" + "\t".join(names)]
        lines += [
            gene + "\t" + "\t".join(table[gene][n] for n in names)
            for gene in sorted(table)
        ]
        return ("\n".join(lines) + "\n").encode()

    return details + "\n", matrix(sense), matrix(antisense)


async def _upload_curated_counts() -> str:
    """Upload the curated study's counts as the account's own, and return the VDI id."""
    details, sense, antisense = await _curated_counts()
    created = await get_vdi_client(_SITE).create_rnaseqrc(
        details=VdiDatasetPostMeta(
            type=RNASEQRC,
            install_targets=[_PROJECT],
            name=_UPLOAD_NAME,
            summary="Created by the PathFinder live lane and deleted after the check.",
        ),
        upload=RnaSeqRcUpload(
            counts=(
                RnaSeqCountFile(name="HS_counts_sense.tsv", content=io.BytesIO(sense)),
                RnaSeqCountFile(
                    name="HS_counts_antisense.tsv", content=io.BytesIO(antisense)
                ),
            ),
            sample_details=details,
        ),
    )
    return created.dataset_id


async def _await_install(client: httpx.AsyncClient, vdi_id: str) -> _Upload:
    """Poll on the site's schedule until the upload installs and its study is listed."""
    vdi = get_vdi_client(_SITE)
    started = time.monotonic()
    outcome, polls = VdiInstallDisposition.CONTINUE, 0
    while outcome not in {
        VdiInstallDisposition.INSTALLED,
        VdiInstallDisposition.FAILED,
    }:
        assert time.monotonic() - started < _INSTALL_BUDGET_SECONDS
        await asyncio.sleep(poll_interval_seconds(polls, outcome))
        polls += 1
        status = (await vdi.get(vdi_id)).status
        outcome = status.disposition(_PROJECT)
        assert outcome is not VdiInstallDisposition.FAILED, (
            f"VEuPathDB did not install {vdi_id}: {status.failure_messages(_PROJECT)}"
        )
    install_seconds = round(time.monotonic() - started, 1)
    while (found := await _installed(client)) is None:
        assert time.monotonic() - started < _INSTALL_BUDGET_SECONDS
        await asyncio.sleep(2)
    return _Upload(
        dataset_id=found[0],
        vdi_id=vdi_id,
        created_here=True,
        install_seconds=install_seconds,
    )


async def _delete_and_confirm(vdi_id: str) -> None:
    vdi = get_vdi_client(_SITE)
    await vdi.delete(vdi_id)
    with pytest.raises(VdiDatasetGoneError):
        await vdi.get(vdi_id)
    listed = await vdi.list_datasets(_PROJECT)
    assert vdi_id not in {row.dataset_id for row in listed}


@pytest.fixture
async def researcher(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    signed_in_to_veupathdb: None,
    require_wdk_creds: str,
) -> AsyncGenerator[tuple[httpx.AsyncClient, UUID]]:
    """A thread held by a researcher signed in as the registered account."""
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    conversation_id = uuid4()
    async with attach_application(), session_maker() as session:
        user = await make_user(session)
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user.id,
                site_id=_SITE,
            )
        )
        await session.commit()
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        async with client_for(app, user.id, wdk_token=require_wdk_creds) as client:
            yield client, conversation_id
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@pytest.fixture
async def installed_upload(
    researcher: tuple[httpx.AsyncClient, UUID],
) -> AsyncGenerator[_Upload]:
    """An installed upload of the account; one made here is deleted afterwards."""
    client, _conversation_id = researcher
    owned = await _installed(client)
    if owned is not None:
        yield _Upload(dataset_id=owned[0], vdi_id=owned[1], created_here=False)
        return
    vdi_id = await _upload_curated_counts()
    try:
        yield await _await_install(client, vdi_id)
    finally:
        await _delete_and_confirm(vdi_id)


async def _patch(client: httpx.AsyncClient, conversation_id: UUID, body: object) -> Any:
    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda", json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _study_entities(dataset_id: str) -> tuple[str, str, str]:
    """The counts entity, its sample entity, and the annotator's genotype variable."""
    entry, study = await get_study_detail_for_dataset(_SITE, dataset_id)
    tree = describe_study(permission_facts(entry), study, dataset_id=dataset_id)
    counts = next(e for e in tree.entities if e.has_gene_id)
    samples = str(counts.parent_entity_id)
    variables = describe_study(
        permission_facts(entry), study, dataset_id=dataset_id, entity_id=samples
    ).variables
    genotype = next(v for v in variables if v.display_name.lower() == "genotype")
    return counts.entity_id, samples, genotype.variable_id


class _Progress(TaskProgressEmitter):
    """Keeps no update: the check reads the compute's summary, not its progress."""

    def __init__(self, conversation_id: UUID) -> None:
        super().__init__(
            task_id=uuid4(),
            conversation_id=conversation_id,
            session_factory=async_session_factory,
        )

    async def update(
        self,
        *,
        percent: float,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        del percent, message, data


async def _computed(
    conversation_id: UUID, *, counts: str, samples: str, genotype: str
) -> None:
    """Run the comparison the way the agent does: the durable compute's body."""
    result = await asyncio.wait_for(
        run_eda_compute_impl(
            context=Context(
                site_id=_SITE,
                user_id=uuid4(),
                strategy_session=StrategySession(site_id=_SITE),
                db_session_factory=no_database,
                cancel_event=asyncio.Event(),
            ),
            task_id=uuid4(),
            conversation_id=conversation_id,
            progress=_Progress(conversation_id),
            memory_store=None,
            identifier_variable={"entityId": counts, "variableId": "VEUPATHDB_GENE_ID"},
            value_variable={
                "entityId": counts,
                "variableId": "SEQUENCE_READ_COUNT_SENSE",
            },
            comparator_variable={"entityId": samples, "variableId": genotype},
            group_a_labels=[_GROUP_A],
            group_b_labels=[_GROUP_B],
        ),
        timeout=_COMPUTE_BUDGET_SECONDS,
    )
    assert result["status"] == "complete", result


async def test_an_installed_upload_exports_the_count_the_site_answers(
    researcher: tuple[httpx.AsyncClient, UUID],
    installed_upload: _Upload,
    drift_log: DriftLog,
) -> None:
    client, conversation_id = researcher
    upload = installed_upload
    analysis_id: str | None = None
    wdk_strategy_id: int | None = None
    try:
        bound = await _patch(
            client,
            conversation_id,
            {"action": "bind", "siteId": _SITE, "datasetId": upload.dataset_id},
        )
        analysis_id = str(bound["analysis"]["analysisId"])
        counts, samples, genotype = await _study_entities(upload.dataset_id)
        await _computed(
            conversation_id, counts=counts, samples=samples, genotype=genotype
        )
        volcano = await client.post(
            f"/api/v1/eda/viz?siteId={_SITE}&conversationId={conversation_id}",
            json={"chart": "volcano"},
        )
        assert volcano.status_code == 200, volcano.text
        exported = (
            await _patch(
                client, conversation_id, {"action": "export-step", "source": "volcano"}
            )
        )["step"]
        wdk_strategy_id = exported["wdkStrategyId"]
        step = next(
            s
            for s in exported["steps"]
            if s["searchName"] == "GenesByEdaVizWithCompute"
        )
        answered = await get_strategy_api(_SITE).get_step_count(step["wdkStepId"])

        retained = volcano.json()["retainedPoints"]
        for check, observed in (
            ("private-dataset-install-seconds", upload.install_seconds),
            ("private-dataset-volcano-retained", retained),
            ("private-dataset-answer-count", answered),
        ):
            drift_log.record(
                site=_SITE, check=check, subject=upload.dataset_id, observed=observed
            )
        drift_log.record(
            site=_SITE,
            check="private-dataset-step-size",
            subject=upload.dataset_id,
            expected=answered,
            observed=step["estimatedSize"],
        )
        assert step["estimatedSize"] == answered
        assert 0 < answered <= retained
    finally:
        if wdk_strategy_id is not None:
            with contextlib.suppress(Exception):
                await get_strategy_api(_SITE).delete_strategy(wdk_strategy_id)
        if analysis_id is not None:
            with contextlib.suppress(Exception):
                await get_eda_analyses_client(_SITE).delete(
                    user_id=await resolve_eda_user_id(_SITE), analysis_id=analysis_id
                )
