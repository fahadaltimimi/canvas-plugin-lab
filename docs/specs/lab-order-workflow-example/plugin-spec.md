# Lab Order Workflow Example Plugin Spec

## Summary

This plugin is a learning example for the JScreen/Phytest-style Canvas workflow.
It accepts a simplified genetic-screening checkout payload through a custom
Canvas Simple API endpoint, creates and tracks an example lab-order workflow
state, and records when the related Canvas order reaches `sent`.

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
- screening type
- test choice
- review requirement
- checkout submission metadata

The plugin:

1. validates the request payload
2. maps the payload into an example Canvas lab-order workflow record
3. creates a tracked example state row
4. sets the initial workflow status:
   - `needs_review` when manual review is required
   - `ready_to_send` when the example treats the request as auto-approvable
5. returns a structured JSON response with identifiers and current state
6. listens for the related Canvas lab order to become `sent`
7. records that `sent` transition as the final state in the example workflow

## Trigger Surface And Workflow Location

### Inbound Trigger

- custom HTTP endpoint exposed by a Canvas Simple API handler
- intended caller: an external purchase-flow application

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
  "canvas_order_id": "ord_456",
  "workflow_status": "ready_to_send",
  "next_action": "await_canvas_send"
}
```

## Tracked Example State

- `request_id`
- `external_checkout_id`
- `canvas_patient_id`
- `canvas_order_id`
- `screening_type`
- `test_code`
- `requires_manual_review`
- `workflow_status`
- `sent_at`

## Assumptions And Constraints

- This is a teaching plugin, not a production integration.
- The payload shape is simplified and uses genetic-screening-flavored terms.
- ECS-style requests default to auto-approval unless
  `requires_manual_review=true`.
- Manual-review requests stop at `needs_review`.
- The plugin owns only the Canvas-side workflow boundary.
- In production, another system would consume the `sent` result and decide
  whether shipment or another downstream handoff should proceed.

## Implementation Shape

- one workflow-scoped plugin: `lab-order-workflow-example`
- one Simple API endpoint for intake
- one lab-order state handler for `sent` tracking
- one small custom-data namespace for durable example state
- one custom model for the tracked workflow row

## Acceptance Criteria

- A valid ECS payload returns a 200 response and creates tracked workflow state
  with `ready_to_send`.
- A valid payload requiring manual review returns a 200 response and creates
  tracked workflow state with `needs_review`.
- An invalid payload returns a 400 response and does not create tracked state.
- A `LAB_ORDER_UPDATED` event for a known order in `sent` state updates the
  tracked workflow row and records `sent_at`.
- A `LAB_ORDER_UPDATED` event for an unknown order is handled safely and does
  not crash.
- The plugin documentation states clearly that downstream shipment release is
  out of scope for this example.
