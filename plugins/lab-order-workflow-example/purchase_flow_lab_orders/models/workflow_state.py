from django.db.models import (
    JSONField,
    BooleanField,
    CharField,
    DateTimeField,
    UniqueConstraint,
)

from canvas_sdk.v1.data.base import CustomModel


class WorkflowStatus:
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    READY_TO_SEND = "ready_to_send"
    SENT = "sent"
    choices = (
        (DRAFT, "Draft"),
        (NEEDS_REVIEW, "Needs review"),
        (READY_TO_SEND, "Ready to send"),
        (SENT, "Sent"),
    )


class LabOrderWorkflowState(CustomModel):
    created = DateTimeField(auto_now_add=True)
    modified = DateTimeField(auto_now=True)
    request_id = CharField(max_length=64)
    external_checkout_id = CharField(max_length=128)
    canvas_patient_id = CharField(max_length=64)
    note_uuid = CharField(max_length=64)
    canvas_order_id = CharField(max_length=64, null=True, blank=True)
    command_uuid = CharField(max_length=64)
    lab_partner = CharField(max_length=128)
    test_order_codes = JSONField(default=list)
    screening_type = CharField(max_length=32)
    test_code = CharField(max_length=64)
    requires_manual_review = BooleanField(default=False)
    workflow_status = CharField(max_length=32, choices=WorkflowStatus.choices)
    sent_at = DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["request_id"], name="uq_workflow_request_id"),
            UniqueConstraint(fields=["canvas_order_id"], name="uq_workflow_canvas_order_id"),
        ]
