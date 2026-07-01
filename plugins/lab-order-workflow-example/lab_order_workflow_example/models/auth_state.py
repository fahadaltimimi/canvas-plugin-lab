from django.db.models import CharField, DateTimeField, UniqueConstraint

from canvas_sdk.v1.data.base import CustomModel


class HMACNonceRecord(CustomModel):
    created = DateTimeField(auto_now_add=True)
    modified = DateTimeField(auto_now=True)
    client_id = CharField(max_length=128)
    nonce = CharField(max_length=128)
    request_timestamp = DateTimeField()
    seen_at = DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["client_id", "nonce"], name="uq_hmac_client_nonce"),
        ]
