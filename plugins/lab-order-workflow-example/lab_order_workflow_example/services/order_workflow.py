from typing import Any

from lab_order_workflow_example.models import LabOrderWorkflowState, WorkflowStatus
from lab_order_workflow_example.services.payload_mapper import MappedLabOrderRequest
from lab_order_workflow_example.services.state_store import (
    create_draft_workflow_state,
    mark_as_sent,
    update_workflow_status,
)


def determine_initial_status(payload: MappedLabOrderRequest) -> str:
    if payload.requires_manual_review:
        return WorkflowStatus.NEEDS_REVIEW

    return WorkflowStatus.READY_TO_SEND


def next_action_for_status(workflow_status: str) -> str:
    if workflow_status == WorkflowStatus.NEEDS_REVIEW:
        return "manual_review"

    return "await_canvas_send"


def start_workflow(payload: MappedLabOrderRequest) -> LabOrderWorkflowState:
    workflow_state = create_draft_workflow_state(payload)
    initial_status = determine_initial_status(payload)
    return update_workflow_status(workflow_state, initial_status)


def extract_order_state(context: dict[str, Any]) -> str | None:
    for key in ("state", "order_state", "status"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()

    return None


def update_workflow_for_sent_order(canvas_order_id: str) -> LabOrderWorkflowState | None:
    return mark_as_sent(canvas_order_id)
