# Lab Order Workflow Example Plugin Spec

## Summary

This plugin is a learning example for the JScreen/Phytest-style Canvas workflow.
It accepts a simplified genetic-screening checkout payload through a custom
Canvas Simple API endpoint, optionally creates a dedicated Canvas review note,
originates a real Canvas lab-order command, tracks workflow state, and records
when the related Canvas order reaches `sent`.

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

1. validates the request payload
2. maps the payload into a note-and-order workflow input
3. uses the supplied `note_uuid`, or creates a dedicated Canvas review note
4. originates a real Canvas lab order on that note
5. creates a tracked workflow state row
6. sets the initial workflow status:
   - `needs_review` when manual review is required
   - `ready_to_send` when the example treats the request as auto-approvable
7. returns a structured JSON response with identifiers and current state
8. exposes a temporary read endpoint so instance testing can inspect stored
   workflow state by `request_id` or `canvas_order_id`
9. stamps the request ID into the lab-order comment so later Canvas events can
   be reconciled back to the purchase request
10. listens for the related Canvas lab order to become `sent`
11. backfills the real Canvas lab-order ID once observed
12. records that `sent` transition as the final state in the example workflow

## Trigger Surface And Workflow Location

### Inbound Trigger

- custom HTTP endpoint exposed by a Canvas Simple API handler
- intended caller: an external purchase-flow application

### Validation Trigger

- custom HTTP read endpoint exposed by the same Canvas Simple API handler
- intended caller: developer/UAT validation during learning and debugging

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
    "note_type_id": "note_type_uuid",
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

## Example Read Response Payload

```json
{
  "request_id": "req_123",
  "external_checkout_id": "chk_123",
  "canvas_patient_id": "pat_123",
  "note_uuid": "6bb7d9d8-6e9d-4c6e-8c0b-7f4f1f17d2d1",
  "canvas_order_id": "ord_456",
  "command_uuid": "cmd_123",
  "lab_partner": "Generic Lab",
  "test_order_codes": ["INT03"],
  "screening_type": "ecs",
  "test_code": "ECS_STANDARD",
  "requires_manual_review": false,
  "workflow_status": "ready_to_send",
  "sent_at": null
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

## Note Resolution

`note_uuid` is the UUID primary key of a Canvas `Note`. The Canvas SDK requires
it to originate a lab-order command.

This example supports two paths:

1. the caller provides `note_uuid` for an existing Canvas note
2. the caller omits `note_uuid` and instead provides `note_creation` so the
   plugin can create a dedicated review note and use that UUID

`note_creation` requires:

- `note_type_id`
- `provider_id`
- `practice_location_id`
- optional `title`
- optional `supervising_provider_id`

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
- one Simple API endpoint for intake
- one temporary Simple API read endpoint for workflow-state inspection
- one lab-order state handler for `sent` tracking
- one small custom-data namespace for durable example state
- one custom model for the tracked workflow row
- optional review-note creation via `Note(...).create()`
- real Canvas lab-order origination via `LabOrderCommand`
- request-ID correlation via the lab-order comment

## Acceptance Criteria

- A valid ECS payload returns a 200 response and creates tracked workflow state
  with `ready_to_send`.
- A valid payload requiring manual review returns a 200 response and creates
  tracked workflow state with `needs_review`.
- A valid payload must include either `note_uuid` or `note_creation`.
- A valid payload must include `test_order_codes`.
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
- A GET request with either `request_id` or `canvas_order_id` returns the
  current tracked workflow row.
- A GET request with neither or both lookup parameters returns a 400 response.
- A GET request for an unknown workflow row returns a 404 response.
- The plugin documentation states clearly that downstream shipment release is
  out of scope for this example.
