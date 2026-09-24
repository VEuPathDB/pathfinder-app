"""Worker-side durable tool implementations.

The worker calls :func:`register_all_tools` from its ``amain`` entrypoint so
that every durable tool's real body is bound before it starts pulling jobs off
the queue. Agent-side wrappers simply submit the job and defer their call.
"""

from __future__ import annotations

from assistant_core.tasks.declaration import register_durable_impl

from pathfinder.ai.tools.standalone.eda_compute import EDA_COMPUTE
from pathfinder.ai.tools.standalone.experiment import CONTROL_TESTS
from pathfinder.ai.tools.standalone.optimization import PARAMETER_SWEEP
from pathfinder.jobs import tasks
from pathfinder.jobs.impls.control_tests_impl import (
    run_control_tests_on_step_impl,
)
from pathfinder.jobs.impls.eda_compute_impl import run_eda_compute_impl
from pathfinder.jobs.impls.optimize_params_impl import (
    optimize_search_parameters_impl,
)


def register_all_tools() -> None:
    """Register every durable tool implementation.

    Also fires ``tasks.ensure_registered`` so the ``@procrastinate_app.task``
    decorators in ``pathfinder.jobs.tasks`` run (as an import side effect)
    before the worker starts pulling jobs. Safe to call repeatedly.
    """
    tasks.ensure_registered()
    register_durable_impl(CONTROL_TESTS, run_control_tests_on_step_impl)
    register_durable_impl(PARAMETER_SWEEP, optimize_search_parameters_impl)
    register_durable_impl(EDA_COMPUTE, run_eda_compute_impl)
