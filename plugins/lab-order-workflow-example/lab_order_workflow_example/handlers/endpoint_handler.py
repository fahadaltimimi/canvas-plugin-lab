from http import HTTPStatus

from canvas_sdk.effects import Effect
from canvas_sdk.effects.simple_api import JSONResponse
from canvas_sdk.handlers.simple_api import Credentials, SimpleAPIRoute
from logger import log

from lab_order_workflow_example.services import (
    InvalidPayloadError,
    map_checkout_payload,
    next_action_for_status,
    start_workflow,
)


class LabOrderWorkflowIntakeEndpoint(SimpleAPIRoute):
    PATH = "/lab-order-workflow-example/orders"

    def authenticate(self, credentials: Credentials) -> bool:
        return True

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
