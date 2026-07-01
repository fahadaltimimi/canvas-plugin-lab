from types import SimpleNamespace

import pytest
from canvas_sdk.events import EventType

from lab_order_workflow_example.handlers.order_state_handler import LabOrderSentStateHandler
from lab_order_workflow_example.models import LabOrderWorkflowState
from lab_order_workflow_example.services import order_workflow


def test_sent_state_updates_known_order() -> None:
    workflow_state = LabOrderWorkflowState.objects.create(
        request_id="req_known",
        external_checkout_id="chk_known",
        canvas_patient_id="pat_known",
        note_uuid="note_known",
        canvas_order_id="ord_known",
        command_uuid="cmd_known",
        lab_partner="Generic Lab",
        test_order_codes=["INT03"],
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


def test_sent_state_backfills_real_canvas_order_id_from_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow_state = LabOrderWorkflowState.objects.create(
        request_id="req_backfill",
        external_checkout_id="chk_backfill",
        canvas_patient_id="pat_backfill",
        note_uuid="note_backfill",
        canvas_order_id=None,
        command_uuid="cmd_backfill",
        lab_partner="Generic Lab",
        test_order_codes=["INT01"],
        screening_type="ecs",
        test_code="ECS_STANDARD",
        requires_manual_review=False,
        workflow_status="ready_to_send",
    )

    monkeypatch.setattr(
        order_workflow,
        "_load_canvas_order_snapshot",
        lambda _: {
            "id": "real_ord_123",
            "comment": "workflow:req_backfill",
            "note_id": "note_backfill",
        },
    )

    mock_event = SimpleNamespace(
        type=EventType.LAB_ORDER_UPDATED,
        context={"state": "sent"},
        target=SimpleNamespace(id="real_ord_123"),
    )

    handler = LabOrderSentStateHandler(event=mock_event)

    effects = handler.compute()
    workflow_state.refresh_from_db()

    assert effects == []
    assert workflow_state.canvas_order_id == "real_ord_123"
    assert workflow_state.workflow_status == "sent"
    assert workflow_state.sent_at is not None


def test_unknown_order_event_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(order_workflow, "_load_canvas_order_snapshot", lambda _: None)

    mock_event = SimpleNamespace(
        type=EventType.LAB_ORDER_UPDATED,
        context={"state": "sent"},
        target=SimpleNamespace(id="ord_unknown"),
    )

    handler = LabOrderSentStateHandler(event=mock_event)

    effects = handler.compute()

    assert effects == []
    assert LabOrderWorkflowState.objects.count() == 0
