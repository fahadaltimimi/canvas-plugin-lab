import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from canvas_sdk.events import EventType
from canvas_sdk.handlers.simple_api.exceptions import AuthenticationError

from lab_order_workflow_example.handlers.endpoint_handler import LabOrderWorkflowIntakeEndpoint
from lab_order_workflow_example.services import (
    HMACCredentials,
    build_canonical_string,
    validate_hmac_credentials,
)

DEFAULT_PATH = "/lab-order-workflow-example/orders"
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
    timestamp: str,
    nonce: str = "nonce_123",
) -> dict[str, str]:
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


def _build_request(
    payload: dict,
    *,
    headers: dict[str, str],
    method: str = "POST",
    path: str = DEFAULT_PATH,
    query_string: str = "",
):
    raw_body = _json_bytes(payload)
    handler = LabOrderWorkflowIntakeEndpoint(
        event=SimpleNamespace(
            type=EventType.SIMPLE_API_REQUEST,
            context={
                "method": method,
                "path": path,
                "query_string": query_string,
                "body": base64.b64encode(raw_body).decode(),
                "headers": headers,
            },
            target=SimpleNamespace(id=""),
        ),
        secrets=DEFAULT_HMAC_SECRETS,
    )
    return handler.request


def test_valid_signed_request_is_accepted() -> None:
    payload = {"hello": "world"}
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    headers = _build_signed_headers(_json_bytes(payload), timestamp=timestamp)
    request = _build_request(payload, headers=headers)

    validate_hmac_credentials(
        HMACCredentials(request),
        DEFAULT_HMAC_SECRETS,
        consume_replay_nonce=True,
    )


def test_wrong_body_hash_is_rejected() -> None:
    payload = {"hello": "world"}
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    headers = _build_signed_headers(_json_bytes(payload), timestamp=timestamp)
    headers["X-Canvas-Content-SHA256"] = "0" * 64
    request = _build_request(payload, headers=headers)

    with pytest.raises(AuthenticationError):
        validate_hmac_credentials(
            HMACCredentials(request),
            DEFAULT_HMAC_SECRETS,
            consume_replay_nonce=True,
        )


def test_wrong_signature_is_rejected() -> None:
    payload = {"hello": "world"}
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    headers = _build_signed_headers(_json_bytes(payload), timestamp=timestamp)
    headers["X-Canvas-Signature"] = "f" * 64
    request = _build_request(payload, headers=headers)

    with pytest.raises(AuthenticationError):
        validate_hmac_credentials(
            HMACCredentials(request),
            DEFAULT_HMAC_SECRETS,
            consume_replay_nonce=True,
        )


def test_expired_timestamp_is_rejected() -> None:
    payload = {"hello": "world"}
    timestamp = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat().replace(
        "+00:00", "Z"
    )
    headers = _build_signed_headers(_json_bytes(payload), timestamp=timestamp)
    request = _build_request(payload, headers=headers)

    with pytest.raises(AuthenticationError):
        validate_hmac_credentials(
            HMACCredentials(request),
            DEFAULT_HMAC_SECRETS,
            consume_replay_nonce=True,
        )


def test_replayed_nonce_is_rejected() -> None:
    payload = {"hello": "world"}
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    headers = _build_signed_headers(_json_bytes(payload), timestamp=timestamp, nonce="replay_nonce")
    request = _build_request(payload, headers=headers)
    credentials = HMACCredentials(request)

    validate_hmac_credentials(
        credentials,
        DEFAULT_HMAC_SECRETS,
        consume_replay_nonce=True,
    )

    with pytest.raises(AuthenticationError):
        validate_hmac_credentials(
            credentials,
            DEFAULT_HMAC_SECRETS,
            consume_replay_nonce=True,
        )
