import base64
import json
from types import SimpleNamespace

import pytest
from canvas_sdk.effects import Effect, EffectType
from canvas_sdk.events import EventType

from lab_order_workflow_example.handlers.endpoint_handler import LabOrderWorkflowIntakeEndpoint
from lab_order_workflow_example.models import LabOrderWorkflowState
from lab_order_workflow_example.services import order_workflow


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
    response_effects = [effect for effect in effects if effect.type == EffectType.SIMPLE_API_RESPONSE]
    assert len(response_effects) == 1

    response_payload = json.loads(response_effects[0].payload)
    response_body = json.loads(base64.b64decode(response_payload["body"]).decode())
    return response_payload["status_code"], response_body


class _FakeNote:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        type(self).calls.append(kwargs)

    def create(self) -> Effect:
        return Effect(type="CREATE_NOTE", payload="{}")


class _FakeLabOrderCommand:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        type(self).calls.append(kwargs)

    def originate(self) -> Effect:
        return Effect(type="ORIGINATE_LAB_ORDER_COMMAND", payload="{}")


class _FakeNoteTypeQuerySet:
    def __init__(self, matches: list[dict]) -> None:
        self.matches = matches

    def values(self, *_args) -> list[dict]:
        return list(self.matches)


class _FakeNoteTypeManager:
    matches: list[dict] = []

    def filter(self, **filters) -> _FakeNoteTypeQuerySet:
        filtered_matches = []
        for match in type(self).matches:
            if all(match.get(key) == value for key, value in filters.items()):
                filtered_matches.append(match)
        return _FakeNoteTypeQuerySet(filtered_matches)


class _FakeNoteType:
    objects = _FakeNoteTypeManager()


@pytest.fixture(autouse=True)
def _stub_canvas_effect_builders(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeNote.calls = []
    _FakeLabOrderCommand.calls = []
    _FakeNoteTypeManager.matches = [
        {
            "id": "nt_review_uuid",
            "system": "https://jscreen.org/fhir/CodeSystem/note-types",
            "code": "genetic-test-order-review",
            "name": "Genetic Test Order Review",
            "is_active": True,
        }
    ]
    monkeypatch.setattr(order_workflow, "Note", _FakeNote)
    monkeypatch.setattr(order_workflow, "LabOrderCommand", _FakeLabOrderCommand)
    monkeypatch.setattr(order_workflow, "NoteType", _FakeNoteType)


def test_endpoint_creates_note_and_ready_to_send_workflow_state() -> None:
    payload = {
        "external_checkout_id": "chk_123",
        "patient": {
            "canvas_patient_id": "pat_123",
            "first_name": "Jane",
            "last_name": "Doe",
            "dob": "1990-01-01",
        },
        "note_creation": {
            "note_type_system": "https://jscreen.org/fhir/CodeSystem/note-types",
            "note_type_code": "genetic-test-order-review",
            "provider_id": "staff_gc",
            "practice_location_id": "pl_main",
            "title": "Genetic test order review",
        },
        "lab_partner": "Generic Lab",
        "test_order_codes": ["INT03"],
        "screening_type": "ecs",
        "test_code": "ECS_STANDARD",
        "ashkenazi_jewish_ancestry": False,
        "requires_manual_review": False,
        "submitted_at": "2026-07-01T10:00:00Z",
    }

    handler = LabOrderWorkflowIntakeEndpoint(event=_build_simple_api_event(payload))

    effects = handler.compute()
    status_code, response = _parse_json_response(effects)
    workflow_state = LabOrderWorkflowState.objects.get(request_id=response["request_id"])

    assert status_code == 200
    assert response["workflow_status"] == "ready_to_send"
    assert response["next_action"] == "await_canvas_send"
    assert response["canvas_order_id"] is None
    assert response["note_uuid"] == workflow_state.note_uuid
    assert response["command_uuid"] == workflow_state.command_uuid

    assert len(effects) == 3
    assert _FakeNote.calls[0]["instance_id"] == workflow_state.note_uuid
    assert _FakeNote.calls[0]["note_type_id"] == "nt_review_uuid"
    assert _FakeLabOrderCommand.calls[0]["note_uuid"] == workflow_state.note_uuid
    assert _FakeLabOrderCommand.calls[0]["tests_order_codes"] == ["INT03"]
    assert _FakeLabOrderCommand.calls[0]["comment"] == f"workflow:{workflow_state.request_id}"

    assert workflow_state.external_checkout_id == "chk_123"
    assert workflow_state.canvas_order_id is None
    assert workflow_state.workflow_status == "ready_to_send"
    assert workflow_state.lab_partner == "Generic Lab"
    assert workflow_state.test_order_codes == ["INT03"]


def test_endpoint_uses_existing_note_for_manual_review_request() -> None:
    payload = {
        "external_checkout_id": "chk_manual_123",
        "patient": {
            "canvas_patient_id": "pat_456",
            "first_name": "Ari",
            "last_name": "Lee",
            "dob": "1988-02-03",
        },
        "note_uuid": "note_existing_123",
        "test_order_codes": ["INT01", "INT02"],
        "screening_type": "cancer",
        "test_code": "CANCER_STANDARD",
        "ashkenazi_jewish_ancestry": True,
        "requires_manual_review": True,
        "submitted_at": "2026-07-01T10:00:00Z",
    }

    handler = LabOrderWorkflowIntakeEndpoint(event=_build_simple_api_event(payload))

    effects = handler.compute()
    status_code, response = _parse_json_response(effects)
    workflow_state = LabOrderWorkflowState.objects.get(request_id=response["request_id"])

    assert status_code == 200
    assert response["workflow_status"] == "needs_review"
    assert response["next_action"] == "manual_review"
    assert response["note_uuid"] == "note_existing_123"

    assert len(effects) == 2
    assert _FakeNote.calls == []
    assert _FakeLabOrderCommand.calls[0]["note_uuid"] == "note_existing_123"
    assert _FakeLabOrderCommand.calls[0]["lab_partner"] == "Generic Lab"
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


def test_endpoint_rejects_ambiguous_note_type_resolution_without_creating_state() -> None:
    _FakeNoteTypeManager.matches = [
        {
            "id": "nt_review_uuid_a",
            "system": "https://jscreen.org/fhir/CodeSystem/note-types",
            "code": "genetic-test-order-review",
            "name": "Genetic Test Order Review A",
            "is_active": True,
        },
        {
            "id": "nt_review_uuid_b",
            "system": "https://other.example/fhir/CodeSystem/note-types",
            "code": "genetic-test-order-review",
            "name": "Genetic Test Order Review B",
            "is_active": True,
        },
    ]
    payload = {
        "external_checkout_id": "chk_ambiguous_123",
        "patient": {
            "canvas_patient_id": "pat_123",
            "first_name": "Jane",
            "last_name": "Doe",
            "dob": "1990-01-01",
        },
        "note_creation": {
            "note_type_code": "genetic-test-order-review",
            "provider_id": "staff_gc",
            "practice_location_id": "pl_main",
        },
        "test_order_codes": ["INT03"],
        "screening_type": "ecs",
        "test_code": "ECS_STANDARD",
        "ashkenazi_jewish_ancestry": False,
        "requires_manual_review": False,
        "submitted_at": "2026-07-01T10:00:00Z",
    }

    handler = LabOrderWorkflowIntakeEndpoint(event=_build_simple_api_event(payload))

    status_code, response = _parse_json_response(handler.compute())

    assert status_code == 400
    assert response["error"] == "invalid_request"
    assert response["details"] == [
        {
            "field": "note_creation.note_type_system|note_creation.note_type_code",
            "message": "provided note_creation filters matched multiple active Canvas note types",
        }
    ]
    assert LabOrderWorkflowState.objects.count() == 0


def test_get_endpoint_returns_workflow_state_by_request_id() -> None:
    workflow_state = LabOrderWorkflowState.objects.create(
        request_id="req_lookup",
        external_checkout_id="chk_lookup",
        canvas_patient_id="pat_lookup",
        note_uuid="note_lookup",
        canvas_order_id=None,
        command_uuid="cmd_lookup",
        lab_partner="Generic Lab",
        test_order_codes=["INT03"],
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
    assert response["note_uuid"] == workflow_state.note_uuid
    assert response["canvas_order_id"] is None
    assert response["command_uuid"] == workflow_state.command_uuid
    assert response["test_order_codes"] == ["INT03"]
    assert response["workflow_status"] == "ready_to_send"
    assert response["sent_at"] is None


def test_get_endpoint_returns_workflow_state_by_canvas_order_id() -> None:
    workflow_state = LabOrderWorkflowState.objects.create(
        request_id="req_order_lookup",
        external_checkout_id="chk_order_lookup",
        canvas_patient_id="pat_order_lookup",
        note_uuid="note_order_lookup",
        canvas_order_id="real_ord_lookup",
        command_uuid="cmd_order_lookup",
        lab_partner="Generic Lab",
        test_order_codes=["INT01", "INT02"],
        screening_type="cancer",
        test_code="CANCER_STANDARD",
        requires_manual_review=True,
        workflow_status="needs_review",
    )

    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_simple_api_event(
            method="GET",
            query_string="canvas_order_id=real_ord_lookup",
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
