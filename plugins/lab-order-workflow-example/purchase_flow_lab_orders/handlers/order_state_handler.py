from canvas_sdk.effects import Effect
from canvas_sdk.events import EventType
from canvas_sdk.handlers import BaseHandler
from logger import log

from purchase_flow_lab_orders.services import (
    extract_order_state,
    update_workflow_for_canvas_order_event,
)


class LabOrderSentStateHandler(BaseHandler):
    RESPONDS_TO = EventType.Name(EventType.LAB_ORDER_UPDATED)

    def compute(self) -> list[Effect]:
        order_state = extract_order_state(self.event.context)
        updated_state = update_workflow_for_canvas_order_event(self.event.target.id, self.event.context)
        if updated_state is None:
            log.info(
                "[LabOrderSentStateHandler] Ignored %s event for unknown canvas_order_id=%s",
                order_state or "unknown-state",
                self.event.target.id,
            )
            return []

        if order_state == "sent":
            log.info(
                "[LabOrderSentStateHandler] Marked canvas_order_id=%s as sent",
                self.event.target.id,
            )
        else:
            log.info(
                "[LabOrderSentStateHandler] Linked request_id=%s to canvas_order_id=%s state=%s",
                updated_state.request_id,
                self.event.target.id,
                order_state or "unknown",
            )
        return []
