from typing import Any

from canvas_sdk.commands import LabOrderCommand
from canvas_sdk.effects import Effect
from canvas_sdk.effects.note import Note
from canvas_sdk.v1.data import LabOrder, NoteType

from purchase_flow_lab_orders.models import LabOrderWorkflowState, WorkflowStatus
from purchase_flow_lab_orders.services.payload_mapper import (
    InvalidPayloadError,
    MappedLabOrderRequest,
    NoteCreationContext,
)
from purchase_flow_lab_orders.services.state_store import (
    assign_canvas_order_id,
    create_draft_workflow_state,
    find_by_canvas_order_id,
    find_by_request_id,
    find_latest_pending_by_note_uuid,
    generate_command_uuid,
    generate_note_uuid,
    generate_request_id,
    mark_as_sent,
    update_workflow_status,
)

ORDER_COMMENT_PREFIX = "workflow:"


def determine_initial_status(payload: MappedLabOrderRequest) -> str:
    if payload.requires_manual_review:
        return WorkflowStatus.NEEDS_REVIEW

    return WorkflowStatus.READY_TO_SEND


def next_action_for_status(workflow_status: str) -> str:
    if workflow_status == WorkflowStatus.NEEDS_REVIEW:
        return "manual_review"

    return "await_canvas_send"


def start_workflow(payload: MappedLabOrderRequest) -> tuple[LabOrderWorkflowState, list[Effect]]:
    request_id = generate_request_id()
    command_uuid = generate_command_uuid()
    note_uuid = payload.note_uuid or generate_note_uuid()

    effects = build_workflow_effects(payload, request_id, note_uuid, command_uuid)

    workflow_state = create_draft_workflow_state(
        payload,
        request_id=request_id,
        note_uuid=note_uuid,
        command_uuid=command_uuid,
    )
    initial_status = determine_initial_status(payload)
    update_workflow_status(workflow_state, initial_status)
    return workflow_state, effects


def build_workflow_effects(
    payload: MappedLabOrderRequest,
    request_id: str,
    note_uuid: str,
    command_uuid: str,
) -> list[Effect]:
    effects: list[Effect] = []

    if payload.note_creation_context is not None:
        effects.append(_build_note_create_effect(payload, note_uuid))

    effects.append(_build_lab_order_originate_effect(payload, request_id, note_uuid, command_uuid))
    return effects


def _build_note_create_effect(payload: MappedLabOrderRequest, note_uuid: str) -> Effect:
    assert payload.note_creation_context is not None

    title = payload.note_creation_context.title or _default_note_title(payload)
    note_type_id = resolve_note_type_id(payload.note_creation_context)
    note_effect = Note(
        instance_id=note_uuid,
        note_type_id=note_type_id,
        patient_id=payload.canvas_patient_id,
        provider_id=payload.note_creation_context.provider_id,
        practice_location_id=payload.note_creation_context.practice_location_id,
        datetime_of_service=payload.submitted_at,
        title=title,
        supervising_provider_id=payload.note_creation_context.supervising_provider_id,
        related_data={
            "source": "purchase_flow",
            "external_checkout_id": payload.external_checkout_id,
            "screening_type": payload.screening_type,
            "test_code": payload.test_code,
        },
    )
    return note_effect.create()


def _build_lab_order_originate_effect(
    payload: MappedLabOrderRequest,
    request_id: str,
    note_uuid: str,
    command_uuid: str,
) -> Effect:
    order_command = LabOrderCommand(
        note_uuid=note_uuid,
        command_uuid=command_uuid,
        lab_partner=payload.lab_partner,
        tests_order_codes=payload.test_order_codes,
        comment=_order_comment_for_request(request_id),
    )
    return order_command.originate()


def _default_note_title(payload: MappedLabOrderRequest) -> str:
    return (
        f"Genetic test order review: {payload.screening_type.upper()} "
        f"({payload.external_checkout_id})"
    )


def _order_comment_for_request(request_id: str) -> str:
    return f"{ORDER_COMMENT_PREFIX}{request_id}"


def resolve_note_type_id(note_creation_context: NoteCreationContext) -> str:
    matches = list(_find_matching_note_types(note_creation_context))

    if not matches:
        raise InvalidPayloadError(
            [
                {
                    "field": "note_creation.note_type_system|note_creation.note_type_code",
                    "message": "no active Canvas note type matched the provided note_creation filters",
                }
            ]
        )

    if len(matches) > 1:
        raise InvalidPayloadError(
            [
                {
                    "field": "note_creation.note_type_system|note_creation.note_type_code",
                    "message": "provided note_creation filters matched multiple active Canvas note types",
                }
            ]
        )

    return str(matches[0]["id"])


def _find_matching_note_types(note_creation_context: NoteCreationContext) -> list[dict[str, str]]:
    filters: dict[str, str | bool] = {"is_active": True}

    if note_creation_context.note_type_system is not None:
        filters["system"] = note_creation_context.note_type_system

    if note_creation_context.note_type_code is not None:
        filters["code"] = note_creation_context.note_type_code

    return list(NoteType.objects.filter(**filters).values("id", "system", "code", "name"))


def extract_request_id_from_order_comment(comment: str | None) -> str | None:
    if not isinstance(comment, str):
        return None

    normalized = comment.strip()
    if not normalized.startswith(ORDER_COMMENT_PREFIX):
        return None

    request_id = normalized.removeprefix(ORDER_COMMENT_PREFIX).strip()
    return request_id or None


def extract_order_state(context: dict[str, Any]) -> str | None:
    for key in ("state", "order_state", "status"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()

    return None


def update_workflow_for_canvas_order_event(
    canvas_order_id: str,
    context: dict[str, Any],
) -> LabOrderWorkflowState | None:
    workflow_state = find_by_canvas_order_id(canvas_order_id)

    if workflow_state is None:
        order_snapshot = _load_canvas_order_snapshot(canvas_order_id)
        if order_snapshot is None:
            return None

        request_id = extract_request_id_from_order_comment(order_snapshot.get("comment"))
        if request_id is not None:
            workflow_state = find_by_request_id(request_id)

        if workflow_state is None:
            note_uuid = order_snapshot.get("note_id")
            if isinstance(note_uuid, str) and note_uuid.strip():
                workflow_state = find_latest_pending_by_note_uuid(note_uuid)

        if workflow_state is None:
            return None

        workflow_state = assign_canvas_order_id(workflow_state, canvas_order_id)

    if extract_order_state(context) == WorkflowStatus.SENT:
        return mark_as_sent(canvas_order_id)

    return workflow_state


def _load_canvas_order_snapshot(canvas_order_id: str) -> dict[str, Any] | None:
    return (
        LabOrder.objects.filter(id=canvas_order_id)
        .values("id", "comment", "note_id")
        .first()
    )
