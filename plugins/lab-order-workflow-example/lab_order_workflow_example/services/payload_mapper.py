from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


class InvalidPayloadError(ValueError):
    def __init__(self, details: list[dict[str, str]]) -> None:
        super().__init__("Invalid lab-order workflow payload")
        self.details = details


@dataclass(frozen=True)
class MappedLabOrderRequest:
    external_checkout_id: str
    canvas_patient_id: str
    patient_first_name: str
    patient_last_name: str
    patient_dob: date
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


def map_checkout_payload(raw_payload: dict[str, Any]) -> MappedLabOrderRequest:
    payload = _require_dict(raw_payload, "root")
    patient = _require_dict(payload.get("patient"), "patient")

    screening_type = _require_string(payload.get("screening_type"), "screening_type").lower()
    if screening_type not in {"ecs", "cancer"}:
        raise InvalidPayloadError(
            [{"field": "screening_type", "message": "must be one of: ecs, cancer"}]
        )

    return MappedLabOrderRequest(
        external_checkout_id=_require_string(
            payload.get("external_checkout_id"), "external_checkout_id"
        ),
        canvas_patient_id=_require_string(patient.get("canvas_patient_id"), "patient.canvas_patient_id"),
        patient_first_name=_require_string(patient.get("first_name"), "patient.first_name"),
        patient_last_name=_require_string(patient.get("last_name"), "patient.last_name"),
        patient_dob=_require_date(patient.get("dob"), "patient.dob"),
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
