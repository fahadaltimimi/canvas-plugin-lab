# Lab Order Workflow Example Plugin Spec

## Summary

This plugin is a learning example for the JScreen/Phytest-style Canvas workflow.
It accepts a simplified genetic-screening checkout payload through a custom
Canvas Simple API endpoint, optionally creates a dedicated Canvas review note,
originates a real Canvas lab-order command, tracks workflow state, and records
when the related Canvas order reaches `sent`.

The intake endpoint is intended to be callable only by an authenticated
external purchase-flow backend. It uses HMAC-signed server-to-server requests,
rejects replayed nonces, and does not expose a debug/read HTTP route.

This example intentionally stops at the Canvas-side boundary. It does not
implement downstream shipment release, Clarity LIMS, DNA Genotek, questionnaire
sync, or consent/document handling.

## Problem Statement

The real integration needs a safe way for an external checkout flow to hand
structured purchase data into Canvas so Canvas can own the lab-order workflow.
The example should demonstrate that architecture without adding production
complexity that obscures the core flow.

## User-Facing Behavior

An external client sends a POST request to a plugin endpoint with:

- patient identity
- either `note_uuid` or `note_creation`
- `test_order_codes` for the real Canvas/Health Gorilla tests to order
- screening type
- test choice
- review requirement
- checkout submission metadata
- optional `lab_partner`

For the current `jlab-dev` instance, the plugin may default `lab_partner` to
`Generic Lab` because that instance currently has a single configured lab.

The plugin:

1. authenticates the caller using an HMAC-signed request contract
2. validates the request payload
3. maps the payload into a note-and-order workflow input
4. uses the supplied `note_uuid`, or creates a dedicated Canvas review note
5. originates a real Canvas lab order on that note
6. creates a tracked workflow state row
7. sets the initial workflow status:
   - `needs_review` when manual review is required
   - `ready_to_send` when the example treats the request as auto-approvable
8. returns a structured JSON response with identifiers and current state
9. stamps the request ID into the lab-order comment so later Canvas events can
   be reconciled back to the purchase request
10. listens for the related Canvas lab order to become `sent`
11. backfills the real Canvas lab-order ID once observed
12. records that `sent` transition as the final state in the example workflow

## Trigger Surface And Workflow Location

### Inbound Trigger

- custom HTTP endpoint exposed by a Canvas Simple API handler
- intended caller: an external purchase-flow application
- requires authenticated server-to-server HMAC headers

### Canvas-Side Follow-Up Trigger

- a Canvas `LAB_ORDER_UPDATED` event handler
- the handler treats the `sent` order state as the final state for this example

## Example Request Payload

```json
{
  "external_checkout_id": "chk_123",
  "patient": {
    "canvas_patient_id": "pat_123",
    "first_name": "Jane",
    "last_name": "Doe",
    "dob": "1990-01-01"
  },
  "note_creation": {
    "note_type_system": "https://jscreen.org/fhir/CodeSystem/note-types",
    "note_type_code": "genetic-test-order-review",
    "provider_id": "staff_uuid",
    "practice_location_id": "location_uuid",
    "title": "Genetic test order review"
  },
  "lab_partner": "Generic Lab",
  "test_order_codes": ["INT03"],
  "screening_type": "ecs",
  "test_code": "ECS_STANDARD",
  "ashkenazi_jewish_ancestry": false,
  "requires_manual_review": false,
  "submitted_at": "2026-07-01T10:00:00Z"
}
```

## Example Authentication Headers

```text
X-Canvas-Client-Id: purchase-flow-dev
X-Canvas-Timestamp: 2026-07-01T18:30:00Z
X-Canvas-Nonce: 6d6f3f3e-f0a4-4d51-987f-33c9b81ab2f0
X-Canvas-Content-SHA256: 8e7d...raw-body-sha256...
X-Canvas-Signature: 9d2a...hmac-sha256...
```

## Example Response Payload

```json
{
  "request_id": "req_123",
  "canvas_order_id": null,
  "command_uuid": "cmd_123",
  "workflow_status": "ready_to_send",
  "next_action": "await_canvas_send",
  "note_uuid": "6bb7d9d8-6e9d-4c6e-8c0b-7f4f1f17d2d1"
}
```

## Tracked Example State

- `request_id`
- `external_checkout_id`
- `canvas_patient_id`
- `note_uuid`
- `canvas_order_id` once backfilled from a Canvas order event
- `command_uuid`
- `lab_partner`
- `test_order_codes`
- `screening_type`
- `test_code`
- `requires_manual_review`
- `workflow_status`
- `sent_at`

## Endpoint Authentication

The production-style intake path should use HMAC-signed server-to-server
authentication rather than open access, Canvas browser session auth, or a
simple reusable API key.

### Why This Is The Chosen Approach

- the caller is an external backend service, not a logged-in Canvas user
- the request carries structured patient and order data
- the plugin should validate both caller identity and request integrity
- the plugin should reject replayed requests
- the design should not require OAuth or Canvas platform changes

### Authentication Contract

The caller sends these headers on every authenticated request:

- `X-Canvas-Client-Id`
- `X-Canvas-Timestamp`
- `X-Canvas-Nonce`
- `X-Canvas-Content-SHA256`
- `X-Canvas-Signature`

The plugin stores the shared secret in Canvas plugin secrets.

For the first implementation, assume one external caller per environment:

- `simpleapi-hmac-client-id`
- `simpleapi-hmac-shared-secret`

This example intentionally exposes only those two plugin secrets in Canvas
admin. Secret rotation support is out of scope for v1 and would require either
a brief coordinated cutover or a future enhancement to reintroduce dual-secret
validation.

### Canonical String

The caller computes:

1. `content_sha256` as the lowercase hex SHA-256 of the raw request body bytes
2. `canonical_target` as:
   - the request path for requests without a query string
   - the request path plus the exact query string for requests with one
3. `signature_input` as the following newline-delimited string:

```text
<HTTP_METHOD>
<CANONICAL_TARGET>
<X-Canvas-Timestamp>
<X-Canvas-Nonce>
<X-Canvas-Content-SHA256>
```

4. `X-Canvas-Signature` as the lowercase hex HMAC-SHA256 of
   `signature_input`, keyed by the shared secret

### Verification Rules

The plugin must:

1. require all HMAC headers
2. verify `X-Canvas-Client-Id` matches the configured client id
3. recompute the raw-body SHA-256 and compare it to
   `X-Canvas-Content-SHA256`
4. recompute the HMAC signature and compare it in constant time
5. reject requests outside the allowed clock-skew window
6. reject replayed nonces inside the replay-protection window

Recommended defaults:

- allowed clock skew: 5 minutes
- nonce replay window: 10 minutes

These are fixed code defaults in the example, not plugin-configurable Canvas
secrets.

### Replay Protection

The plugin should persist the tuple:

- `client_id`
- `nonce`
- `timestamp`
- `seen_at`

Any repeated nonce for the same client id inside the replay window must be
rejected.

For this learning plugin, a small plugin-backed cache keyed by
`client_id + nonce` is acceptable. Production durability or a more formal
distributed-cache design is out of scope.

### Environment Behavior

- `POST /lab-order-workflow-example/orders` must require HMAC auth
- the plugin must not expose a public/debug workflow read endpoint

### Error Behavior

Authentication failures return:

- `401 unauthorized` for missing, malformed, expired, replayed, or invalid HMAC
  credentials
- a structured JSON error body that does not leak the shared secret or the
  computed signature

Example error shape:

```json
{
  "error": "unauthorized"
}
```

## Note Resolution

`note_uuid` is the UUID primary key of a Canvas `Note`. The Canvas SDK requires
it to originate a lab-order command.

This example supports two paths:

1. the caller provides `note_uuid` for an existing Canvas note
2. the caller omits `note_uuid` and instead provides `note_creation` so the
   plugin can create a dedicated review note and use that UUID

`note_creation` requires:

- at least one of `note_type_system` or `note_type_code`
- `provider_id`
- `practice_location_id`
- optional `title`
- optional `supervising_provider_id`

The plugin resolves the actual Canvas `NoteType.id` internally:

1. if both `note_type_system` and `note_type_code` are provided, it resolves an
   exact active match
2. if only one is provided, it resolves only when that filter returns exactly
   one active Canvas note type
3. if the match is missing or ambiguous, the plugin returns a validation error

For production-style use, the recommended request shape is to provide both
`note_type_system` and `note_type_code` so the note type is explicit and
portable across instances without leaking UUIDs into the external purchase
flow.

For the real purchase-flow use case, the default recommendation is to let the
plugin create a dedicated review note rather than forcing the external caller to
know a note UUID ahead of time.

Clinically, that review note should be a dedicated asynchronous order-review
note type rather than a schedulable or billable encounter note.

## Canvas Order ID Timing

The real Canvas `LabOrder.id` is not known synchronously when the intake
endpoint returns. The plugin therefore:

1. returns `request_id`, `note_uuid`, and `command_uuid` immediately
2. stores a correlation token in the lab-order comment using the request ID
3. backfills `canvas_order_id` later when Canvas emits a lab-order update event

## Assumptions And Constraints

- This is a teaching plugin, not a production integration.
- The payload shape is simplified and uses genetic-screening-flavored terms.
- the unauthenticated endpoint behavior is no longer acceptable for the
  purchase-flow use case
- the caller must provide either `note_uuid` or `note_creation`
- `test_order_codes` is required because the instance has many configured lab
  tests and there is no single safe default test.
- `lab_partner` may default to `Generic Lab` in the current instance, but the
  request contract should still allow it to be overridden.
- ECS-style requests default to auto-approval unless
  `requires_manual_review=true`.
- Manual-review requests stop at `needs_review`.
- The plugin owns only the Canvas-side workflow boundary.
- In production, another system would consume the `sent` result and decide
  whether shipment or another downstream handoff should proceed.

## Implementation Shape

- one workflow-scoped plugin: `lab-order-workflow-example`
- one HMAC-protected Simple API endpoint for intake
- one lab-order state handler for `sent` tracking
- one small custom-data namespace for durable example state
- one custom model for the tracked workflow row
- one small replay-protection store for seen nonces
- optional review-note creation via `Note(...).create()`
- real Canvas lab-order origination via `LabOrderCommand`
- request-ID correlation via the lab-order comment

## Bruno Tooling Update

The Bruno collection under `/Users/fahad/Documents/Dev/canvas-plugin-lab/bruno`
must be updated alongside the auth change.

Required changes:

- remove the assumption that requests are open or only use inherited auth
- add the HMAC header set to the POST request examples
- move shared values into Bruno environment variables where possible:
  - `CANVAS_BASE_URL`
  - `HMAC_CLIENT_ID`
  - `HMAC_SHARED_SECRET`
  - `EXTERNAL_CHECKOUT_ID`
  - `CANVAS_PATIENT_ID`
  - `PATIENT_FIRST_NAME`
  - `PATIENT_LAST_NAME`
  - `PATIENT_DOB`
  - `NOTE_TYPE_SYSTEM`
  - `NOTE_TYPE_CODE`
  - `PROVIDER_ID`
  - `PRACTICE_LOCATION_ID`
  - `NOTE_TITLE`
  - `LAB_PARTNER`
  - `TEST_ORDER_CODES_JSON`
  - `SCREENING_TYPE`
  - `TEST_CODE`
  - `ASHKENAZI_JEWISH_ANCESTRY`
  - `REQUIRES_MANUAL_REVIEW`
  - `SUBMITTED_AT`
- if Bruno scripting is used, compute:
  - timestamp
  - nonce
  - raw-body SHA-256
  - canonical target
  - HMAC signature
- remove the debug GET request from the collection
- add an example Bruno environment template to the repo, not real secrets

The Bruno collection should remain a UAT tool only. It must never contain real
production secrets.

## Acceptance Criteria

- A valid ECS payload returns a 200 response and creates tracked workflow state
  with `ready_to_send`.
- A valid payload requiring manual review returns a 200 response and creates
  tracked workflow state with `needs_review`.
- A POST request without valid HMAC authentication returns `401`.
- A request with an expired timestamp returns `401`.
- A request with a reused nonce inside the replay window returns `401`.
- A request with a mismatched body hash or signature returns `401`.
- A valid payload must include either `note_uuid` or `note_creation`.
- A valid payload must include `test_order_codes`.
- If `note_creation` is used, it must include at least one of
  `note_type_system` or `note_type_code`.
- If `note_creation` resolves zero or multiple active Canvas note types, the
  plugin returns a 400 response and does not create tracked state.
- If `lab_partner` is omitted, the plugin defaults it to `Generic Lab` for the
  current instance.
- If `note_creation` is used, the plugin emits a Canvas note-create effect
  before the lab-order command effect.
- The initial intake response may contain `canvas_order_id=null` until a later
  Canvas lab-order event backfills the real ID.
- An invalid payload returns a 400 response and does not create tracked state.
- A `LAB_ORDER_UPDATED` event for a known order in `sent` state updates the
  tracked workflow row and records `sent_at`.
- A `LAB_ORDER_UPDATED` event for an unknown order is handled safely and does
  not crash.
- No public/debug workflow-state read endpoint is exposed.
- The Bruno request examples include authenticated request headers or a Bruno
  mechanism for computing them.
- The plugin documentation states clearly that downstream shipment release is
  out of scope for this example.
