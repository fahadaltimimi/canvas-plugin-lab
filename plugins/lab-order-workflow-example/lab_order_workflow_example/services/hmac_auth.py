from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from canvas_sdk.handlers.simple_api import Credentials
from canvas_sdk.handlers.simple_api.exceptions import AuthenticationError
from logger import log

from lab_order_workflow_example.services.state_store import consume_nonce, purge_expired_nonces

if TYPE_CHECKING:
    from canvas_sdk.handlers.simple_api.api import Request


HMAC_CLIENT_ID_HEADER = "X-Canvas-Client-Id"
HMAC_TIMESTAMP_HEADER = "X-Canvas-Timestamp"
HMAC_NONCE_HEADER = "X-Canvas-Nonce"
HMAC_CONTENT_SHA256_HEADER = "X-Canvas-Content-SHA256"
HMAC_SIGNATURE_HEADER = "X-Canvas-Signature"

HMAC_CLIENT_ID_SECRET = "simpleapi-hmac-client-id"
HMAC_SHARED_SECRET = "simpleapi-hmac-shared-secret"
HMAC_PREVIOUS_SHARED_SECRET = "simpleapi-hmac-previous-shared-secret"
HMAC_ALLOWED_SKEW_SECONDS = "simpleapi-hmac-allowed-skew-seconds"
HMAC_REPLAY_WINDOW_SECONDS = "simpleapi-hmac-replay-window-seconds"

DEFAULT_ALLOWED_SKEW_SECONDS = 300
DEFAULT_REPLAY_WINDOW_SECONDS = 600


class HMACAuthenticationError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("Request authentication failed")


@dataclass(frozen=True)
class HMACConfig:
    client_id: str
    shared_secret: str
    previous_shared_secret: str | None
    allowed_skew_seconds: int
    replay_window_seconds: int


class HMACCredentials(Credentials):
    def __init__(self, request: Request) -> None:
        super().__init__(request)
        self.request = request
        self.client_id = _normalize_header_value(request.headers.get(HMAC_CLIENT_ID_HEADER))
        self.timestamp = _normalize_header_value(request.headers.get(HMAC_TIMESTAMP_HEADER))
        self.nonce = _normalize_header_value(request.headers.get(HMAC_NONCE_HEADER))
        self.content_sha256 = _normalize_header_value(
            request.headers.get(HMAC_CONTENT_SHA256_HEADER)
        )
        self.signature = _normalize_header_value(request.headers.get(HMAC_SIGNATURE_HEADER))


def validate_hmac_request(
    request: Request,
    secrets: dict[str, Any],
    *,
    consume_replay_nonce: bool,
    now: datetime | None = None,
) -> None:
    validate_hmac_credentials(
        HMACCredentials(request),
        secrets,
        consume_replay_nonce=consume_replay_nonce,
        now=now,
    )


def validate_hmac_credentials(
    credentials: HMACCredentials,
    secrets: dict[str, Any],
    *,
    consume_replay_nonce: bool,
    now: datetime | None = None,
) -> None:
    config = _load_hmac_config(secrets)
    _require_required_headers(credentials)

    if not hmac.compare_digest(credentials.client_id.encode(), config.client_id.encode()):
        raise HMACAuthenticationError()

    current_time = now or datetime.now(timezone.utc)
    request_timestamp = _parse_timestamp(credentials.timestamp)
    _validate_timestamp(request_timestamp, current_time, config.allowed_skew_seconds)

    computed_content_hash = hashlib.sha256(credentials.request.body).hexdigest()
    if not hmac.compare_digest(credentials.content_sha256.lower(), computed_content_hash):
        raise HMACAuthenticationError()

    canonical_string = build_canonical_string(
        method=credentials.request.method,
        path=credentials.request.path,
        query_string=credentials.request.query_string,
        timestamp=credentials.timestamp,
        nonce=credentials.nonce,
        content_sha256=credentials.content_sha256.lower(),
    )

    valid_signatures = [
        _sign_canonical_string(canonical_string, config.shared_secret),
    ]
    if config.previous_shared_secret:
        valid_signatures.append(
            _sign_canonical_string(canonical_string, config.previous_shared_secret)
        )

    provided_signature = credentials.signature.lower()
    if not any(
        hmac.compare_digest(provided_signature, valid_signature)
        for valid_signature in valid_signatures
    ):
        raise HMACAuthenticationError()

    purge_expired_nonces(config.replay_window_seconds, now=current_time)
    if consume_replay_nonce and not consume_nonce(
        client_id=credentials.client_id,
        nonce=credentials.nonce,
        request_timestamp=request_timestamp,
    ):
        raise HMACAuthenticationError()


def build_canonical_string(
    *,
    method: str,
    path: str,
    query_string: str,
    timestamp: str,
    nonce: str,
    content_sha256: str,
) -> str:
    canonical_target = path
    if query_string:
        canonical_target = f"{canonical_target}?{query_string}"

    return "\n".join(
        [
            method.upper(),
            canonical_target,
            timestamp,
            nonce,
            content_sha256,
        ]
    )


def _load_hmac_config(secrets: dict[str, Any]) -> HMACConfig:
    return HMACConfig(
        client_id=_require_secret_string(secrets, HMAC_CLIENT_ID_SECRET),
        shared_secret=_require_secret_string(secrets, HMAC_SHARED_SECRET),
        previous_shared_secret=_optional_secret_string(secrets, HMAC_PREVIOUS_SHARED_SECRET),
        allowed_skew_seconds=_parse_positive_int_secret(
            secrets,
            HMAC_ALLOWED_SKEW_SECONDS,
            DEFAULT_ALLOWED_SKEW_SECONDS,
        ),
        replay_window_seconds=_parse_positive_int_secret(
            secrets,
            HMAC_REPLAY_WINDOW_SECONDS,
            DEFAULT_REPLAY_WINDOW_SECONDS,
        ),
    )


def _require_required_headers(credentials: HMACCredentials) -> None:
    if not all(
        [
            credentials.client_id,
            credentials.timestamp,
            credentials.nonce,
            credentials.content_sha256,
            credentials.signature,
        ]
    ):
        raise HMACAuthenticationError()


def _parse_timestamp(raw_timestamp: str) -> datetime:
    try:
        parsed_timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HMACAuthenticationError() from exc

    if parsed_timestamp.tzinfo is None:
        raise HMACAuthenticationError()

    return parsed_timestamp.astimezone(timezone.utc)


def _validate_timestamp(
    request_timestamp: datetime,
    now: datetime,
    allowed_skew_seconds: int,
) -> None:
    if abs((now - request_timestamp).total_seconds()) > allowed_skew_seconds:
        raise HMACAuthenticationError()


def _sign_canonical_string(canonical_string: str, secret: str) -> str:
    return hmac.new(
        secret.encode(),
        canonical_string.encode(),
        hashlib.sha256,
    ).hexdigest()


def _normalize_header_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def _require_secret_string(secrets: dict[str, Any], key: str) -> str:
    value = _optional_secret_string(secrets, key)
    if value is None:
        log.error("Missing required HMAC secret '%s'", key)
        raise HMACAuthenticationError()

    return value


def _optional_secret_string(secrets: dict[str, Any], key: str) -> str | None:
    value = secrets.get(key)
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    normalized = value.strip()
    return normalized or None


def _parse_positive_int_secret(
    secrets: dict[str, Any],
    key: str,
    default: int,
) -> int:
    raw_value = secrets.get(key)
    if raw_value is None:
        return default

    try:
        parsed_value = int(str(raw_value).strip())
    except ValueError as exc:
        log.error("Invalid integer value for HMAC secret '%s'", key)
        raise HMACAuthenticationError() from exc

    if parsed_value <= 0:
        log.error("HMAC secret '%s' must be a positive integer", key)
        raise HMACAuthenticationError()

    return parsed_value
