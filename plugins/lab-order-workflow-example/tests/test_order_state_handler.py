from types import SimpleNamespace

from canvas_sdk.events import EventType

from lab_order_workflow_example.handlers.order_state_handler import LabOrderSentStateHandler
from lab_order_workflow_example.models import LabOrderWorkflowState


def test_sent_state_updates_known_order() -> None:
    workflow_state = LabOrderWorkflowState.objects.create(
        request_id="req_known",
        external_checkout_id="chk_known",
        canvas_patient_id="pat_known",
        canvas_order_id="ord_known",
        screening_type="ecs",
        test_code="ECS_STANDARD",
        requires_manual_review=False,
        workflow_status="ready_to_send",
    )

    mock_event = SimpleNamespace(
        type=EventType.LAB_ORDER_UPDATED,
        context={"state": "sent"},
        target=SimpleNamespace(id="ord_known"),
    )

    handler = LabOrderSentStateHandler(event=mock_event)

    effects = handler.compute()
    workflow_state.refresh_from_db()

    assert effects == []
    assert workflow_state.workflow_status == "sent"
    assert workflow_state.sent_at is not None


def test_unknown_order_sent_event_is_safe() -> None:
    mock_event = SimpleNamespace(
        type=EventType.LAB_ORDER_UPDATED,
        context={"state": "sent"},
        target=SimpleNamespace(id="ord_unknown"),
    )

    handler = LabOrderSentStateHandler(event=mock_event)

    effects = handler.compute()

    assert effects == []
    assert LabOrderWorkflowState.objects.count() == 0
