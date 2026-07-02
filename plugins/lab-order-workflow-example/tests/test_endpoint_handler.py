import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from canvas_sdk.effects import Effect, EffectType
from canvas_sdk.events import EventType

from purchase_flow_lab_orders.handlers.endpoint_handler import LabOrderWorkflowIntakeEndpoint
from purchase_flow_lab_orders.models import LabOrderWorkflowState
from purchase_flow_lab_orders.services import build_canonical_string, order_workflow

DEFAULT_PATH = "/orders"
DEFAULT_HMAC_SECRETS = {
    "simpleapi-hmac-client-id": "purchase-flow-dev",
    "simpleapi-hmac-shared-secret": "super-secret-value",
}


def _json_bytes(payload: dict | None) -> bytes:
    return json.dumps(payload or {}).encode()


def _build_signed_headers(
    body: bytes,
    *,
    method: str = "POST",
    path: str = DEFAULT_PATH,
    query_string: str = "",
    client_id: str = "purchase-flow-dev",
    shared_secret: str = "super-secret-value",
    timestamp: str | None = None,
    nonce: str = "nonce_123",
) -> dict[str, str]:
    timestamp = timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    content_sha256 = hashlib.sha256(body).hexdigest()
    canonical_string = build_canonical_string(
        method=method,
        path=path,
        query_string=query_string,
        timestamp=timestamp,
        nonce=nonce,
        content_sha256=content_sha256,
    )
    signature = hmac.new(
        shared_secret.encode(),
        canonical_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    return {
        "Content-Type": "application/json",
        "X-Canvas-Client-Id": client_id,
        "X-Canvas-Timestamp": timestamp,
        "X-Canvas-Nonce": nonce,
        "X-Canvas-Content-SHA256": content_sha256,
        "X-Canvas-Signature": signature,
    }


def _build_simple_api_event(
    payload: dict | None = None,
    *,
    event_type=EventType.SIMPLE_API_REQUEST,
    method: str = "POST",
    path: str = DEFAULT_PATH,
    query_string: str = "",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> SimpleNamespace:
    raw_body = body if body is not None else _json_bytes(payload)
    return SimpleNamespace(
        type=event_type,
        context={
            "method": method,
            "path": path,
            "query_string": query_string,
            "body": base64.b64encode(raw_body).decode(),
            "headers": headers or {"Content-Type": "application/json"},
        },
        target=SimpleNamespace(id=""),
    )


def _build_signed_event(
    payload: dict | None = None,
    *,
    event_type=EventType.SIMPLE_API_REQUEST,
    method: str = "POST",
    path: str = DEFAULT_PATH,
    query_string: str = "",
    body: bytes | None = None,
    headers_override: dict[str, str] | None = None,
    client_id: str = "purchase-flow-dev",
    shared_secret: str = "super-secret-value",
    timestamp: str | None = None,
    nonce: str = "nonce_123",
) -> SimpleNamespace:
    raw_body = body if body is not None else _json_bytes(payload)
    headers = _build_signed_headers(
        raw_body,
        method=method,
        path=path,
        query_string=query_string,
        client_id=client_id,
        shared_secret=shared_secret,
        timestamp=timestamp,
        nonce=nonce,
    )
    if headers_override:
        headers.update(headers_override)

    return _build_simple_api_event(
        payload,
        event_type=event_type,
        method=method,
        path=path,
        query_string=query_string,
        body=raw_body,
        headers=headers,
    )


def _parse_json_response(effects: list[Effect]) -> tuple[int, dict]:
    response_effects = [effect for effect in effects if effect.type == EffectType.SIMPLE_API_RESPONSE]
    assert len(response_effects) == 1

    response_payload = json.loads(response_effects[0].payload)
    response_body = json.loads(base64.b64decode(response_payload["body"]).decode() or "{}")
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


def _create_note_payload(*, requires_manual_review: bool = False) -> dict:
    return {
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
        "requires_manual_review": requires_manual_review,
        "submitted_at": "2026-07-01T10:00:00Z",
    }


def test_endpoint_creates_note_and_ready_to_send_workflow_state() -> None:
    payload = _create_note_payload()
    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_signed_event(payload),
        secrets=DEFAULT_HMAC_SECRETS,
    )

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
    assert workflow_state.workflow_status == "ready_to_send"


def test_preflight_auth_does_not_consume_nonce_before_request() -> None:
    payload = _create_note_payload()
    shared_event = _build_signed_event(payload, nonce="nonce_preflight")
    preflight_context = {
        **shared_event.context,
        "body": base64.b64encode(b"").decode(),
    }

    auth_handler = LabOrderWorkflowIntakeEndpoint(
        event=SimpleNamespace(
            type=EventType.SIMPLE_API_AUTHENTICATE,
            context=preflight_context,
            target=shared_event.target,
        ),
        secrets=DEFAULT_HMAC_SECRETS,
    )
    request_handler = LabOrderWorkflowIntakeEndpoint(
        event=shared_event,
        secrets=DEFAULT_HMAC_SECRETS,
    )

    auth_status_code, auth_response = _parse_json_response(auth_handler.compute())
    request_status_code, request_response = _parse_json_response(request_handler.compute())

    assert auth_status_code == 200
    assert auth_response == {}
    assert request_status_code == 200
    assert request_response["workflow_status"] == "ready_to_send"


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

    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_signed_event(payload, nonce="nonce_manual"),
        secrets=DEFAULT_HMAC_SECRETS,
    )

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
    assert workflow_state.workflow_status == "needs_review"


def test_missing_required_hmac_header_returns_401() -> None:
    payload = _create_note_payload()
    event = _build_signed_event(payload, headers_override={"X-Canvas-Signature": ""}, nonce="nonce_missing")
    handler = LabOrderWorkflowIntakeEndpoint(event=event, secrets=DEFAULT_HMAC_SECRETS)

    status_code, response = _parse_json_response(handler.compute())

    assert status_code == 401
    assert response == {"error": "unauthorized"}
    assert LabOrderWorkflowState.objects.count() == 0


def test_wrong_client_id_returns_401() -> None:
    payload = _create_note_payload()
    event = _build_signed_event(payload, client_id="wrong-client", nonce="nonce_wrong_client")
    handler = LabOrderWorkflowIntakeEndpoint(event=event, secrets=DEFAULT_HMAC_SECRETS)

    status_code, response = _parse_json_response(handler.compute())

    assert status_code == 401
    assert response == {"error": "unauthorized"}
    assert LabOrderWorkflowState.objects.count() == 0


def test_replayed_nonce_returns_401() -> None:
    payload = _create_note_payload()
    event = _build_signed_event(payload, nonce="nonce_replayed")

    first_handler = LabOrderWorkflowIntakeEndpoint(event=event, secrets=DEFAULT_HMAC_SECRETS)
    second_handler = LabOrderWorkflowIntakeEndpoint(event=event, secrets=DEFAULT_HMAC_SECRETS)

    first_status_code, _first_response = _parse_json_response(first_handler.compute())
    second_status_code, second_response = _parse_json_response(second_handler.compute())

    assert first_status_code == 200
    assert second_status_code == 401
    assert second_response == {"error": "unauthorized"}


def test_endpoint_rejects_invalid_payload_after_auth_without_creating_state() -> None:
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

    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_signed_event(payload, nonce="nonce_invalid_payload"),
        secrets=DEFAULT_HMAC_SECRETS,
    )

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

    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_signed_event(payload, nonce="nonce_ambiguous"),
        secrets=DEFAULT_HMAC_SECRETS,
    )

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


def test_removed_get_endpoint_is_not_registered() -> None:
    handler = LabOrderWorkflowIntakeEndpoint(
        event=_build_simple_api_event(
            event_type=EventType.SIMPLE_API_REQUEST,
            method="GET",
            headers={"Content-Type": "application/json"},
        ),
        secrets=DEFAULT_HMAC_SECRETS,
    )

    assert handler.accept_event() is False
