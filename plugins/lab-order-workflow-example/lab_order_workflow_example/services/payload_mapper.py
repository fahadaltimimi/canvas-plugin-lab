from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


class InvalidPayloadError(ValueError):
    def __init__(self, details: list[dict[str, str]]) -> None:
        super().__init__("Invalid lab-order workflow payload")
        self.details = details


@dataclass(frozen=True)
class NoteCreationContext:
    note_type_id: str
    provider_id: str
    practice_location_id: str
    title: str | None
    supervising_provider_id: str | None


@dataclass(frozen=True)
class MappedLabOrderRequest:
    external_checkout_id: str
    canvas_patient_id: str
    patient_first_name: str
    patient_last_name: str
    patient_dob: date
    note_uuid: str | None
    note_creation_context: NoteCreationContext | None
    lab_partner: str
    test_order_codes: list[str]
    screening_type: str
    test_code: str
    ashkenazi_jewish_ancestry: bool
    requires_manual_review: bool
    submitted_at: datetime


def _require_dict(value: Any, field_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise InvalidPayloadError([{"field": field_name, "message": "must be an object"}])


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise InvalidPayloadError([{"field": field_name, "message": "must be a string"}])

    normalized = value.strip()
    if not normalized:
        raise InvalidPayloadError([{"field": field_name, "message": "must not be empty"}])

    return normalized


def _require_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise InvalidPayloadError([{"field": field_name, "message": "must be a boolean"}])


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None

    return _require_string(value, field_name)


def _require_date(value: Any, field_name: str) -> date:
    raw = _require_string(value, field_name)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidPayloadError([{"field": field_name, "message": "must be an ISO date"}]) from exc


def _require_datetime(value: Any, field_name: str) -> datetime:
    raw = _require_string(value, field_name)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidPayloadError(
            [{"field": field_name, "message": "must be an ISO datetime"}]
        ) from exc


def _require_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise InvalidPayloadError([{"field": field_name, "message": "must be an array"}])

    normalized_values = []
    for index, item in enumerate(value):
        normalized_values.append(_require_string(item, f"{field_name}[{index}]"))

    if not normalized_values:
        raise InvalidPayloadError([{"field": field_name, "message": "must not be empty"}])

    return normalized_values


def _map_note_creation_context(value: Any) -> NoteCreationContext:
    context = _require_dict(value, "note_creation")
    return NoteCreationContext(
        note_type_id=_require_string(context.get("note_type_id"), "note_creation.note_type_id"),
        provider_id=_require_string(context.get("provider_id"), "note_creation.provider_id"),
        practice_location_id=_require_string(
            context.get("practice_location_id"),
            "note_creation.practice_location_id",
        ),
        title=_optional_string(context.get("title"), "note_creation.title"),
        supervising_provider_id=_optional_string(
            context.get("supervising_provider_id"),
            "note_creation.supervising_provider_id",
        ),
    )


def map_checkout_payload(raw_payload: dict[str, Any]) -> MappedLabOrderRequest:
    payload = _require_dict(raw_payload, "root")
    patient = _require_dict(payload.get("patient"), "patient")
    note_uuid = _optional_string(payload.get("note_uuid"), "note_uuid")
    note_creation_context = (
        _map_note_creation_context(payload.get("note_creation"))
        if payload.get("note_creation") is not None
        else None
    )

    screening_type = _require_string(payload.get("screening_type"), "screening_type").lower()
    if screening_type not in {"ecs", "cancer"}:
        raise InvalidPayloadError(
            [{"field": "screening_type", "message": "must be one of: ecs, cancer"}]
        )

    if note_uuid is None and note_creation_context is None:
        raise InvalidPayloadError(
            [
                {
                    "field": "note_uuid|note_creation",
                    "message": "provide note_uuid or note_creation",
                }
            ]
        )

    if note_uuid is not None and note_creation_context is not None:
        raise InvalidPayloadError(
            [
                {
                    "field": "note_uuid|note_creation",
                    "message": "provide note_uuid or note_creation, not both",
                }
            ]
        )

    return MappedLabOrderRequest(
        external_checkout_id=_require_string(
            payload.get("external_checkout_id"), "external_checkout_id"
        ),
        canvas_patient_id=_require_string(patient.get("canvas_patient_id"), "patient.canvas_patient_id"),
        patient_first_name=_require_string(patient.get("first_name"), "patient.first_name"),
        patient_last_name=_require_string(patient.get("last_name"), "patient.last_name"),
        patient_dob=_require_date(patient.get("dob"), "patient.dob"),
        note_uuid=note_uuid,
        note_creation_context=note_creation_context,
        lab_partner=_optional_string(payload.get("lab_partner"), "lab_partner") or "Generic Lab",
        test_order_codes=_require_string_list(payload.get("test_order_codes"), "test_order_codes"),
        screening_type=screening_type,
        test_code=_require_string(payload.get("test_code"), "test_code").upper(),
        ashkenazi_jewish_ancestry=_require_bool(
            payload.get("ashkenazi_jewish_ancestry"), "ashkenazi_jewish_ancestry"
        ),
        requires_manual_review=_require_bool(
            payload.get("requires_manual_review"), "requires_manual_review"
        ),
        submitted_at=_require_datetime(payload.get("submitted_at"), "submitted_at"),
    )
