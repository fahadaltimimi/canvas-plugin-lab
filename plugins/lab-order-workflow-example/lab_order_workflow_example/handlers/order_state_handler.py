from canvas_sdk.effects import Effect
from canvas_sdk.events import EventType
from canvas_sdk.handlers import BaseHandler
from logger import log

from lab_order_workflow_example.services import extract_order_state, update_workflow_for_sent_order


class LabOrderSentStateHandler(BaseHandler):
    RESPONDS_TO = EventType.Name(EventType.LAB_ORDER_UPDATED)

    def compute(self) -> list[Effect]:
        order_state = extract_order_state(self.event.context)
        if order_state != "sent":
            return []

        updated_state = update_workflow_for_sent_order(self.event.target.id)
        if updated_state is None:
            log.info(
                "[LabOrderSentStateHandler] Ignored sent event for unknown canvas_order_id=%s",
                self.event.target.id,
            )
            return []

        log.info(
            "[LabOrderSentStateHandler] Marked canvas_order_id=%s as sent",
            self.event.target.id,
        )
        return []
