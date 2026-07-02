import json
from http import HTTPStatus

from canvas_sdk.effects import Effect, EffectType
from canvas_sdk.effects.simple_api import JSONResponse
from canvas_sdk.handlers.simple_api import SimpleAPIRoute
from canvas_sdk.handlers.simple_api.exceptions import AuthenticationError
from logger import log

from purchase_flow_lab_orders.services import (
    HMACCredentials,
    InvalidPayloadError,
    map_checkout_payload,
    next_action_for_status,
    start_workflow,
    validate_hmac_credentials,
    validate_hmac_request,
)


class LabOrderWorkflowIntakeEndpoint(SimpleAPIRoute):
    PATH = "/orders"

    def authenticate(self, credentials: HMACCredentials) -> bool:
        validate_hmac_credentials(
            credentials,
            self.secrets,
            consume_replay_nonce=False,
            require_body_hash_match=False,
        )
        return True

    def _authenticate(self) -> list[Effect]:
        try:
            self.authenticate(HMACCredentials(self.request))
        except AuthenticationError as error:
            log.info(
                "[LabOrderWorkflowIntakeEndpoint] SIMPLE_API_AUTHENTICATE rejected request: %s",
                error,
            )
            return [
                JSONResponse(
                    content={"error": "unauthorized"},
                    status_code=HTTPStatus.UNAUTHORIZED,
                ).apply()
            ]

        payload = {
            "headers": {},
            "body": "",
            "status_code": int(HTTPStatus.OK),
            "handling_options": {
                "file_uploads": getattr(self._handler, "file_uploads", "passthrough"),
            },
        }
        return [Effect(type=EffectType.SIMPLE_API_RESPONSE, payload=json.dumps(payload))]

    def post(self) -> list[JSONResponse | Effect]:
        try:
            validate_hmac_request(
                self.request,
                self.secrets,
                consume_replay_nonce=True,
            )
        except AuthenticationError as error:
            log.info(
                "[LabOrderWorkflowIntakeEndpoint] Rejected unauthorized request: %s",
                error,
            )
            return [
                JSONResponse(
                    content={"error": "unauthorized"},
                    status_code=HTTPStatus.UNAUTHORIZED,
                )
            ]

        try:
            mapped_payload = map_checkout_payload(self.request.json())
            workflow_state, workflow_effects = start_workflow(mapped_payload)
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
        else:
            log.info(
                "[LabOrderWorkflowIntakeEndpoint] Created workflow request_id=%s note_uuid=%s canvas_order_id=%s status=%s",
                workflow_state.request_id,
                workflow_state.note_uuid,
                workflow_state.canvas_order_id,
                workflow_state.workflow_status,
            )

        return [
            *workflow_effects,
            JSONResponse(
                content={
                    "request_id": workflow_state.request_id,
                    "canvas_order_id": workflow_state.canvas_order_id,
                    "command_uuid": workflow_state.command_uuid,
                    "note_uuid": workflow_state.note_uuid,
                    "workflow_status": workflow_state.workflow_status,
                    "next_action": next_action_for_status(workflow_state.workflow_status),
                },
                status_code=HTTPStatus.OK,
            )
        ]
