from dataclasses import dataclass, field

from assistant_core.platform.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    StepSettings,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    rebuild_tree,
    settings_of,
    walk,
    wdk_search_name,
)
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb.model import CamelModel
from veupathdb.wdk import StrategyAPI, get_site, get_strategy_api
from veupathdb_mcp.catalog import make_validation_callbacks, validate_parameters

from strategist.domain.strategy.build_outcome import StepPushFailure
from strategist.domain.strategy.operations.apply import PlanDeparturesError
from strategist.domain.strategy.record_class_check import step_class_of
from strategist.domain.strategy.step_status import step_status
from strategist.services.strategies._tree_write import (
    StrategyRole,
    delete_what_the_tree_dropped,
    provision_the_datasets,
    put_the_tree,
    read_the_strategy,
    sync_result,
    undo_the_tree,
)
from strategist.services.strategies._wdk_step_calls import (
    StepWrite,
    _sort_a_ranking,
    finished_step,
    written_step,
)
from strategist.services.strategies.commit_failures import (
    departures,
    unsorted_failure,
    what_wdk_holds,
)
from strategist.services.strategies.reconcile import (
    held_after_the_put,
    held_before_the_commit,
    learn_what_wdk_added,
    reconcile_sync_state_with_wdk,
)
from strategist.services.strategies.record_classes import (
    fill_record_classes,
    unclassed_step_failure,
    what_the_site_cannot_run,
)
from strategist.services.strategies.started_plan import (
    started_settings,
    unstated,
)
from strategist.services.strategies.step_push_planner import (
    CreateAction,
    PatchAction,
    RecreateAction,
    SkipAction,
    StepPushPlan,
    moved_by_the_turn,
    plan_step_pushes,
)
from strategist.services.strategies.step_search import names_a_wdk_question
from strategist.services.strategies.sync import SyncResult
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.services.strategies.wdk_counts import invalidate_counts_for

logger = get_logger(__name__)

_NOT_READY = "not ready to build yet"


class CommitTarget(CamelModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    role: StrategyRole = "thread"
    copies: dict[str, StepSettings] = Field(default_factory=dict)
    datasets: dict[str, list[str]] = Field(default_factory=dict)


class CommittedTree(BaseModel):
    model_config = ConfigDict(frozen=True)

    pushed: list[str] = Field(default_factory=list)
    failures: list[StepPushFailure] = Field(default_factory=list)
    drafts: dict[str, str] = Field(default_factory=dict)
    skipped: list[str] = Field(default_factory=list)
    sync: SyncResult | None = None
    record_type: str | None = None
    held: dict[str, StepSettings] = Field(default_factory=dict)
    put: bool = False

    @property
    def refused(self) -> dict[str, str]:
        return {**self.drafts, **{f.step_id: f.error for f in self.failures}}


@dataclass
class _Commit:
    api: StrategyAPI
    site_id: str
    steps: dict[str, StrategyStep]
    sync_state: WDKSyncState
    before: dict[str, StepSettings]
    started: dict[str, StepSettings]
    pushed: list[str] = field(default_factory=list)
    failures: list[StepPushFailure] = field(default_factory=list)
    drafts: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    sent: dict[str, dict[str, ParamValue]] = field(default_factory=dict)

    @property
    def blocked(self) -> set[str]:
        return {*self.drafts, *self.skipped, *(f.step_id for f in self.failures)}

    def committed(
        self,
        sync: SyncResult | None = None,
        record_type: str | None = None,
        held: dict[str, StepSettings] | None = None,
        *,
        put: bool = False,
    ) -> CommittedTree:
        return CommittedTree(
            pushed=self.pushed,
            failures=self.failures,
            drafts=self.drafts,
            skipped=self.skipped,
            sync=sync,
            record_type=record_type,
            held=held or {},
            put=put,
        )

    async def validate(self, plan: list[StepPushPlan]) -> None:
        callbacks = make_validation_callbacks(self.site_id)
        for entry in plan:
            step = self.steps[entry.step_id]
            record_type = step_class_of(self.steps, step.id) or ""
            if not entry.action.writes_parameters:
                continue
            if not names_a_wdk_question(step) or not record_type:
                self._draft_unless_ready(step)
                continue
            before = self.before.get(step.id, StepSettings()).parameters
            context = unstated(step.parameters, before, self.started.get(step.id))
            try:
                validated = await validate_parameters(
                    SearchContext(
                        site_id=self.site_id,
                        record_type=record_type,
                        search_name=wdk_search_name(step),
                    ),
                    stated={
                        k: v for k, v in step.parameters.items() if k not in context
                    },
                    context=context,
                    held_validation=self.sync_state.step_validations.get(step.id),
                    callbacks=callbacks,
                    about=None,
                )
            except ValidationError as exc:
                self._refused(step, exc)
                continue
            self.sent[step.id] = {**step.parameters, **context, **validated.params}
            step.parameters = {**step.parameters, **validated.params}
            if validated.record_class:
                step.record_class = validated.record_class

    def _draft_unless_ready(self, step: StrategyStep) -> None:
        held = self.sync_state.wdk_step_ids.get(step.id)
        status = step_status(
            step, wdk_step_id=held, validation=None, has_open_params=False
        )
        if held is None and not status.is_pushable:
            self.drafts[step.id] = _NOT_READY

    def _refused(self, step: StrategyStep, exc: ValidationError) -> None:
        detail = exc.detail or exc.title
        if step.id not in self.sync_state.wdk_step_ids:
            self.drafts[step.id] = detail
            return
        self._fail(
            StepPushFailure(
                step_id=step.id,
                search_name=wdk_search_name(step),
                error=detail,
                wdk_status=exc.status,
            )
        )

    def _fail(self, failure: StepPushFailure) -> None:
        self.sync_state.wdk_push_errors[failure.step_id] = failure.error
        self.failures.append(failure)

    async def everything(
        self, plan: list[StepPushPlan], root: StrategyStepNode, target: CommitTarget
    ) -> CommittedTree:
        await self.validate(plan)
        for entry in plan:
            await self.push(entry)
        written = [*self.pushed, *(f.step_id for f in self.failures)]
        invalidate_counts_for(self.sync_state, written, steps=self.steps)
        if self.failures or self.drafts:
            return self.committed()
        return await self.put(root, target)

    async def push(self, entry: StepPushPlan) -> None:
        step = self.steps[entry.step_id]
        blocked = self.blocked
        if step.id in blocked:
            return
        if any(i in blocked for i in step.input_ids()):
            self.skipped.append(step.id)
            return
        match entry.action:
            case SkipAction():
                if self._unfinished(step):
                    await self._finish(step)
            case PatchAction() as action:
                if not self._unfinished(step) or await self._finish(step):
                    await self._write(action, step)
            case CreateAction() | RecreateAction() as action:
                await self._write(action, step)

    def _unfinished(self, step: StrategyStep) -> bool:
        return (
            step.id in self.sync_state.wdk_step_ids
            and step.id in self.sync_state.wdk_push_errors
            and step.filters_wdk_added is None
        )

    async def _finish(self, step: StrategyStep) -> bool:
        record_type = step_class_of(self.steps, step.id)
        if record_type is None:
            self._fail(unclassed_step_failure(step.id, wdk_search_name(step)))
            return False
        failure = await finished_step(self.api, self.sync_state, step, record_type)
        if failure is not None:
            self._fail(failure)
            return False
        self.pushed.append(step.id)
        return True

    async def _write(
        self, action: CreateAction | PatchAction | RecreateAction, step: StrategyStep
    ) -> None:
        record_type = step_class_of(self.steps, step.id)
        if record_type is None:
            self._fail(unclassed_step_failure(step.id, wdk_search_name(step)))
            return
        before = self.before.get(step.id, StepSettings())
        failure, replaced = await written_step(
            self.api,
            self.sync_state,
            step,
            action,
            StepWrite(
                record_type=record_type,
                parameters=self.sent.get(step.id, step.parameters),
                before=before,
                moved=frozenset(
                    moved_by_the_turn(
                        settings_of(step), before, self.started.get(step.id)
                    )
                ),
            ),
        )
        if replaced is not None:
            self.sync_state.replaced_wdk_step_ids.append(replaced)
        if failure is not None:
            self._fail(failure)
            return
        self.sync_state.wdk_push_errors.pop(step.id, None)
        self.pushed.append(step.id)

    async def put(self, root: StrategyStepNode, target: CommitTarget) -> CommittedTree:
        record_type = step_class_of(self.steps, root.id)
        if record_type is None:
            self._fail(
                unclassed_step_failure(root.id, wdk_search_name(self.steps[root.id]))
            )
            return self.committed()
        root_before = self.sync_state.wdk_root_step_id
        try:
            written = await put_the_tree(
                self.api, self.site_id, root, record_type, self.sync_state, target
            )
        except VEuPathDBError as exc:
            site = get_site(self.site_id).display_name
            reason = exc.detail or exc.title
            self._fail(
                StepPushFailure(
                    step_id=root.id,
                    search_name=wdk_search_name(self.steps[root.id]),
                    error=f"{site} did not take the strategy's steps: {reason}",
                )
            )
            return self.committed(record_type=record_type)
        moved = [root.id] if root_before != self.sync_state.wdk_root_step_id else []
        reweighed = [
            sid
            for sid in self.pushed
            if self.before.get(sid, StepSettings()).wdk_weight
            != self.steps[sid].wdk_weight
        ]
        await self._sort(root.id, [*reweighed, *moved])
        await delete_what_the_tree_dropped(self.api, self.steps, self.sync_state)
        held = held_after_the_put(
            await read_the_strategy(self.api, self.sync_state), self.sync_state
        )
        for node in walk(root):
            learn_what_wdk_added(
                self.steps[node.id], node, held.get(node.id), self.before.get(node.id)
            )
            self._departed(node, held.get(node.id))
        sync = (
            None
            if written is None
            else sync_result(self.site_id, root, self.sync_state, written)
        )
        return self.committed(sync=sync, record_type=record_type, held=held, put=True)

    async def _sort(self, root_id: str, moved: list[str]) -> None:
        try:
            await _sort_a_ranking(self.api, self.sync_state, self.steps, root_id, moved)
        except VEuPathDBError as exc:
            self._fail(unsorted_failure(self.site_id, self.steps[root_id], exc))

    def _departed(self, node: StrategyStepNode, holds: StepSettings | None) -> None:
        if holds is None:
            return
        step = self.steps[node.id]
        for failure in departures(
            self.site_id,
            node,
            step,
            holds,
            self.before.get(node.id, StepSettings()),
            step.filters_wdk_added or [],
        ):
            self._fail(failure)


async def commit_tree(
    *,
    site_id: str,
    steps: dict[str, StrategyStep],
    root_id: str,
    old: StrategyAst | None,
    sync_state: WDKSyncState,
    target: CommitTarget,
) -> CommittedTree:
    if target.role != "thread" and (
        sync_state.wdk_step_ids or sync_state.wdk_strategy_id
    ):
        msg = f"a {target.role} strategy is committed from a fresh sync state"
        raise ValueError(msg)
    refused = await what_the_site_cannot_run(site_id, steps, root_id)
    if not refused.empty:
        raise PlanDeparturesError(refused)
    api = get_strategy_api(site_id)
    held = await what_wdk_holds(api, site_id, steps, root_id, old, sync_state)
    match held:
        case StepPushFailure():
            return CommittedTree(failures=[held])
    await provision_the_datasets(api, steps, target.datasets)
    await fill_record_classes(site_id, steps)
    root = rebuild_tree(root_id, steps)
    before = {
        **target.copies,
        **held_before_the_commit(
            old, root, steps, held, unfinished=sync_state.wdk_push_errors
        ),
    }
    plan = plan_step_pushes(
        old_ast=old,
        new_ast=StrategyAst(record_type="", root=root),
        existing_wdk_ids=sync_state.wdk_step_ids,
        held=before,
        unfinished=sync_state.wdk_push_errors,
    )
    started = started_settings(old, sync_state.wdk_push_errors)
    run = _Commit(api, site_id, steps, sync_state, before, started)
    if target.role == "thread":
        return await run.everything(plan, root, target)
    try:
        committed = await run.everything(plan, root, target)
    except VEuPathDBError:
        await undo_the_tree(run.api, sync_state)
        raise
    if committed.refused or committed.sync is None:
        await undo_the_tree(run.api, sync_state)
    elif target.role == "saved":
        await run.api.set_saved(committed.sync.wdk_strategy_id, is_saved=True)
    return committed


async def drop_the_tree(
    *, site_id: str, steps: dict[str, StrategyStep], sync_state: WDKSyncState
) -> None:
    api = get_strategy_api(site_id)
    await reconcile_sync_state_with_wdk(sync_state, api)
    await delete_what_the_tree_dropped(api, steps, sync_state)
