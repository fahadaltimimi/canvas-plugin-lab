from http import HTTPStatus

from canvas_sdk.effects import Effect
from canvas_sdk.effects.simple_api import JSONResponse
from canvas_sdk.handlers.simple_api import Credentials, SimpleAPIRoute
from logger import log

from lab_order_workflow_example.models import LabOrderWorkflowState
from lab_order_workflow_example.services import (
    InvalidPayloadError,
    find_by_canvas_order_id,
    find_by_request_id,
    map_checkout_payload,
    next_action_for_status,
    start_workflow,
)


class LabOrderWorkflowIntakeEndpoint(SimpleAPIRoute):
    PATH = "/lab-order-workflow-example/orders"

    def authenticate(self, credentials: Credentials) -> bool:
        return True

    def get(self) -> list[JSONResponse | Effect]:
        request_id = _normalize_lookup_value(self.request.query_params.get("request_id"))
        canvas_order_id = _normalize_lookup_value(self.request.query_params.get("canvas_order_id"))

        if (request_id is None) == (canvas_order_id is None):
            return [
                JSONResponse(
                    content={
                        "error": "invalid_request",
                        "details": [
                            {
                                "field": "request_id|canvas_order_id",
                                "message": "provide exactly one lookup parameter",
                            }
                        ],
                    },
                    status_code=HTTPStatus.BAD_REQUEST,
                )
            ]

        workflow_state = (
            find_by_request_id(request_id)
            if request_id is not None
            else find_by_canvas_order_id(canvas_order_id)
        )
        if workflow_state is None:
            return [
                JSONResponse(
                    content={"error": "not_found"},
                    status_code=HTTPStatus.NOT_FOUND,
                )
            ]

        return [
            JSONResponse(
                content=_serialize_workflow_state(workflow_state),
                status_code=HTTPStatus.OK,
            )
        ]

    def post(self) -> list[JSONResponse | Effect]:
        try:
            mapped_payload = map_checkout_payload(self.request.json())
        except InvalidPayloadError as error:
            log.info(
                "[LabOrderWorkflowIntakeEndpoint] Rejected invalid request: %s",
                error.details,
            )
            return [
                JSONResponse(
                    content={
                        "error": "invalid_request",
                        "details": error.details,
                    },
                    status_code=HTTPStatus.BAD_REQUEST,
                )
            ]

        workflow_state = start_workflow(mapped_payload)

        log.info(
            "[LabOrderWorkflowIntakeEndpoint] Created workflow request_id=%s canvas_order_id=%s status=%s",
            workflow_state.request_id,
            workflow_state.canvas_order_id,
            workflow_state.workflow_status,
        )

        return [
            JSONResponse(
                content={
                    "request_id": workflow_state.request_id,
                    "canvas_order_id": workflow_state.canvas_order_id,
                    "workflow_status": workflow_state.workflow_status,
                    "next_action": next_action_for_status(workflow_state.workflow_status),
                },
                status_code=HTTPStatus.OK,
            )
        ]


def _normalize_lookup_value(value) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def _serialize_workflow_state(workflow_state: LabOrderWorkflowState) -> dict:
    return {
        "request_id": workflow_state.request_id,
        "external_checkout_id": workflow_state.external_checkout_id,
        "canvas_patient_id": workflow_state.canvas_patient_id,
        "canvas_order_id": workflow_state.canvas_order_id,
        "screening_type": workflow_state.screening_type,
        "test_code": workflow_state.test_code,
        "requires_manual_review": workflow_state.requires_manual_review,
        "workflow_status": workflow_state.workflow_status,
        "sent_at": workflow_state.sent_at.isoformat() if workflow_state.sent_at else None,
    }
