import base64
import json
from types import SimpleNamespace

from canvas_sdk.effects import EffectType
from canvas_sdk.events import EventType

from lab_order_workflow_example.handlers.endpoint_handler import LabOrderWorkflowIntakeEndpoint
from lab_order_workflow_example.models import LabOrderWorkflowState


def _build_simple_api_event(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        type=EventType.SIMPLE_API_REQUEST,
        context={
            "method": "POST",
            "path": "/lab-order-workflow-example/orders",
            "query_string": "",
            "body": base64.b64encode(json.dumps(payload).encode()).decode(),
            "headers": {"Content-Type": "application/json"},
        },
        target=SimpleNamespace(id=""),
    )


def _parse_json_response(effects: list) -> tuple[int, dict]:
    assert len(effects) == 1
    assert effects[0].type == EffectType.SIMPLE_API_RESPONSE

    response_payload = json.loads(effects[0].payload)
    response_body = json.loads(base64.b64decode(response_payload["body"]).decode())
    return response_payload["status_code"], response_body


def test_endpoint_creates_ready_to_send_workflow_state_for_auto_approved_ecs() -> None:
    payload = {
        "external_checkout_id": "chk_123",
        "patient": {
            "canvas_patient_id": "pat_123",
            "first_name": "Jane",
            "last_name": "Doe",
            "dob": "1990-01-01",
        },
        "screening_type": "ecs",
        "test_code": "ECS_STANDARD",
        "ashkenazi_jewish_ancestry": False,
        "requires_manual_review": False,
        "submitted_at": "2026-07-01T10:00:00Z",
    }

    handler = LabOrderWorkflowIntakeEndpoint(event=_build_simple_api_event(payload))

    status_code, response = _parse_json_response(handler.compute())
    workflow_state = LabOrderWorkflowState.objects.get(request_id=response["request_id"])

    assert status_code == 200
    assert response["workflow_status"] == "ready_to_send"
    assert response["next_action"] == "await_canvas_send"
    assert workflow_state.external_checkout_id == "chk_123"
    assert workflow_state.workflow_status == "ready_to_send"
    assert workflow_state.screening_type == "ecs"


def test_endpoint_creates_needs_review_workflow_state_for_manual_review_request() -> None:
    payload = {
        "external_checkout_id": "chk_manual_123",
        "patient": {
            "canvas_patient_id": "pat_456",
            "first_name": "Ari",
            "last_name": "Lee",
            "dob": "1988-02-03",
        },
        "screening_type": "cancer",
        "test_code": "CANCER_STANDARD",
        "ashkenazi_jewish_ancestry": True,
        "requires_manual_review": True,
        "submitted_at": "2026-07-01T10:00:00Z",
    }

    handler = LabOrderWorkflowIntakeEndpoint(event=_build_simple_api_event(payload))

    status_code, response = _parse_json_response(handler.compute())
    workflow_state = LabOrderWorkflowState.objects.get(request_id=response["request_id"])

    assert status_code == 200
    assert response["workflow_status"] == "needs_review"
    assert response["next_action"] == "manual_review"
    assert workflow_state.workflow_status == "needs_review"
    assert workflow_state.requires_manual_review is True


def test_endpoint_rejects_invalid_payload_without_creating_state() -> None:
    payload = {
        "external_checkout_id": "chk_invalid_123",
        "patient": {
            "canvas_patient_id": "pat_999",
            "first_name": "Sam",
            "last_name": "Ng",
            "dob": "1995-02-03",
        },
        "screening_type": "ecs",
        "test_code": "",
        "ashkenazi_jewish_ancestry": False,
        "requires_manual_review": False,
        "submitted_at": "2026-07-01T10:00:00Z",
    }

    handler = LabOrderWorkflowIntakeEndpoint(event=_build_simple_api_event(payload))

    status_code, response = _parse_json_response(handler.compute())

    assert status_code == 400
    assert response["error"] == "invalid_request"
    assert LabOrderWorkflowState.objects.count() == 0

