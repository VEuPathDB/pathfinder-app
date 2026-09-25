"""The parked calls a checkpoint carries, as samples for its serializer."""

from __future__ import annotations

from uuid import UUID

from assistant_core.graph.turn_state import (
    DurableCall,
    PendingApproval,
    PendingDurableCall,
    SubAgentApprovalCall,
    SubAgentApprovalPending,
)


def pending_durable_call() -> PendingDurableCall:
    return PendingDurableCall(
        phase="verification",
        tool_call_id="call_verify_strategy",
        tool_name="verify_strategy",
        tool_args={"reason": "test the built step against the controls"},
        prior_messages_json='[{"kind":"request","parts":[]}]',
        durable_calls=[
            DurableCall(
                tool_call_id="call_run_control_tests_on_step",
                tool_name="run_control_tests_on_step",
                args={"wdk_step_id": 440299573},
                task_id=UUID("0c6100d2-0000-4000-8000-000000000001"),
                durable_tool_name="run_control_tests_on_step",
            ),
        ],
        sub_agent=SubAgentApprovalPending(
            role="verification",
            approvals=[
                SubAgentApprovalCall(
                    tool_call_id="call_run_control_tests_on_step",
                    tool_name="run_control_tests_on_step",
                    args={"wdk_step_id": 440299573},
                ),
            ],
            messages_json='[{"kind":"response","parts":[]}]',
        ),
    )


def pending_approval() -> PendingApproval:
    return PendingApproval(
        phase="verification",
        tool_call_id="call_verify_strategy",
        tool_name="verify_strategy",
        tool_args={"reason": "optimize the fold change"},
        prior_messages_json='[{"kind":"request","parts":[]}]',
        user_message_id=UUID("01a011a9-5c65-74b2-8813-215ab5b382fa"),
        sub_agent=SubAgentApprovalPending(
            role="verification",
            approvals=[
                SubAgentApprovalCall(
                    tool_call_id="call_optimize_search_parameters",
                    tool_name="optimize_search_parameters",
                    args={"settings": {"budget": 8}},
                ),
            ],
            messages_json='[{"kind":"response","parts":[]}]',
        ),
    )
