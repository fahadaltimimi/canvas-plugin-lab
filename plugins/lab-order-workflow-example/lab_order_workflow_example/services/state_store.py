from datetime import datetime, timezone
from uuid import uuid4

from lab_order_workflow_example.models import LabOrderWorkflowState, WorkflowStatus
from lab_order_workflow_example.services.payload_mapper import MappedLabOrderRequest


def generate_request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def generate_command_uuid() -> str:
    return str(uuid4())


def generate_note_uuid() -> str:
    return str(uuid4())


def create_draft_workflow_state(
    payload: MappedLabOrderRequest,
    *,
    request_id: str,
    note_uuid: str,
    command_uuid: str,
) -> LabOrderWorkflowState:
    return LabOrderWorkflowState.objects.create(
        request_id=request_id,
        external_checkout_id=payload.external_checkout_id,
        canvas_patient_id=payload.canvas_patient_id,
        note_uuid=note_uuid,
        canvas_order_id=None,
        command_uuid=command_uuid,
        lab_partner=payload.lab_partner,
        test_order_codes=payload.test_order_codes,
        screening_type=payload.screening_type,
        test_code=payload.test_code,
        requires_manual_review=payload.requires_manual_review,
        workflow_status=WorkflowStatus.DRAFT,
    )


def update_workflow_status(
    workflow_state: LabOrderWorkflowState,
    workflow_status: str,
    *,
    sent_at: datetime | None = None,
) -> LabOrderWorkflowState:
    workflow_state.workflow_status = workflow_status
    if sent_at is not None:
        workflow_state.sent_at = sent_at
    workflow_state.save()
    return workflow_state


def find_by_canvas_order_id(canvas_order_id: str) -> LabOrderWorkflowState | None:
    return LabOrderWorkflowState.objects.filter(canvas_order_id=canvas_order_id).first()


def find_by_request_id(request_id: str) -> LabOrderWorkflowState | None:
    return LabOrderWorkflowState.objects.filter(request_id=request_id).first()


def find_latest_pending_by_note_uuid(note_uuid: str) -> LabOrderWorkflowState | None:
    return (
        LabOrderWorkflowState.objects.filter(note_uuid=note_uuid, canvas_order_id__isnull=True)
        .order_by("-created")
        .first()
    )


def assign_canvas_order_id(
    workflow_state: LabOrderWorkflowState,
    canvas_order_id: str,
) -> LabOrderWorkflowState:
    if workflow_state.canvas_order_id != canvas_order_id:
        workflow_state.canvas_order_id = canvas_order_id
        workflow_state.save(update_fields=["canvas_order_id", "modified"])
    return workflow_state


def mark_as_sent(canvas_order_id: str) -> LabOrderWorkflowState | None:
    workflow_state = find_by_canvas_order_id(canvas_order_id)
    if workflow_state is None:
        return None

    return update_workflow_status(
        workflow_state,
        WorkflowStatus.SENT,
        sent_at=datetime.now(timezone.utc),
    )
