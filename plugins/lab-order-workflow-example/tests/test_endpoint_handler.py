import base64
import json
from types import SimpleNamespace

from canvas_sdk.effects import EffectType
from canvas_sdk.events import EventType

from lab_order_workflow_example.handlers.endpoint_handler import LabOrderWorkflowIntakeEndpoint
from lab_order_workflow_example.models import LabOrderWorkflowState


def _build_simple_api_event(
    payload: dict | None = None,
    *,
    method: str = "POST",
    path: str = "/lab-order-workflow-example/orders",
    query_string: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        type=EventType.SIMPLE_API_REQUEST,
        context={
            "method": method,
            "path": path,
            "query_string": query_string,
            "body": base64.b64encode(json.dumps(payload or {}).encode()).decode(),
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


def test_get_endpoint_returns_workflow_state_by_request_id() -> None:
    workflow_state = LabOrderWorkflowState.objects.create(
        request_id="req_lookup",
        external_checkout_id="chk_lookup",
        canvas_patient_id="pat_lookup",
        canvas_order_id="ord_lookup",
        screening_type="ecs",
        test_code="ECS_STANDARD",
        requires_manual_review=False,
        workflow_status="ready_to_send",
    )

    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_simple_api_event(
            method="GET",
            query_string="request_id=req_lookup",
        )
    )

    status_code, response = _parse_json_response(handler.compute())

    assert status_code == 200
    assert response["request_id"] == workflow_state.request_id
    assert response["canvas_order_id"] == workflow_state.canvas_order_id
    assert response["workflow_status"] == "ready_to_send"
    assert response["sent_at"] is None


def test_get_endpoint_returns_workflow_state_by_canvas_order_id() -> None:
    workflow_state = LabOrderWorkflowState.objects.create(
        request_id="req_order_lookup",
        external_checkout_id="chk_order_lookup",
        canvas_patient_id="pat_order_lookup",
        canvas_order_id="ord_order_lookup",
        screening_type="cancer",
        test_code="CANCER_STANDARD",
        requires_manual_review=True,
        workflow_status="needs_review",
    )

    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_simple_api_event(
            method="GET",
            query_string="canvas_order_id=ord_order_lookup",
        )
    )

    status_code, response = _parse_json_response(handler.compute())

    assert status_code == 200
    assert response["request_id"] == workflow_state.request_id
    assert response["canvas_order_id"] == workflow_state.canvas_order_id
    assert response["workflow_status"] == "needs_review"
    assert response["requires_manual_review"] is True


def test_get_endpoint_requires_exactly_one_lookup_parameter() -> None:
    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_simple_api_event(
            method="GET",
            query_string="request_id=req_lookup&canvas_order_id=ord_lookup",
        )
    )

    status_code, response = _parse_json_response(handler.compute())

    assert status_code == 400
    assert response["error"] == "invalid_request"


def test_get_endpoint_returns_not_found_for_unknown_workflow_state() -> None:
    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_simple_api_event(
            method="GET",
            query_string="request_id=req_missing",
        )
    )

    status_code, response = _parse_json_response(handler.compute())

    assert status_code == 404
    assert response["error"] == "not_found"
