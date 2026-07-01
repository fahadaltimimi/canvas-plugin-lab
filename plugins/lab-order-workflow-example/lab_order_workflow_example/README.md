lab-order-workflow-example
==========================

## Purpose

This is a teaching plugin for a simplified lab-order workflow.

It demonstrates three distinct steps:

1. an external checkout system POSTs structured data into Canvas through a
   custom plugin endpoint
2. the plugin resolves or creates a Canvas review note and originates a real
   Canvas lab-order command
3. the plugin records when the related Canvas lab order reaches `sent`

The example stops at the Canvas-side boundary. In production, another system
would consume the `sent` outcome and decide whether shipment or another
downstream handoff should proceed.

## Endpoint

- `POST /lab-order-workflow-example/orders`
- `GET /lab-order-workflow-example/orders?request_id=<id>`
- `GET /lab-order-workflow-example/orders?canvas_order_id=<id>`

The request uses a simplified genetic-screening payload with patient identity,
screening type, test code, and whether manual review is required. It accepts
either:

- `note_uuid` for an existing Canvas note
- `note_creation` so the plugin can create a dedicated review note

The request also requires real `test_order_codes` and defaults `lab_partner` to
`Generic Lab` when omitted.

The temporary GET endpoint is for learning and UAT. It returns the stored
workflow row when exactly one lookup parameter is provided.

## Workflow Statuses

- `draft`
- `needs_review`
- `ready_to_send`
- `sent`

The endpoint creates `draft` internally, then moves the workflow to either
`needs_review` or `ready_to_send`. The initial response may not know the real
Canvas `LabOrder.id` yet, so the workflow row is correlated by `request_id`,
`note_uuid`, and `command_uuid` first. A separate `LAB_ORDER_UPDATED` handler
backfills the real order ID and marks the workflow as `sent` when the observed
order state is `sent`.

## Notes

- This plugin does not originate a real downstream shipment.
- This plugin does not implement questionnaire syncing or consent storage.
- The manifest controls which handlers Canvas loads; update
  `CANVAS_MANIFEST.json` if handler class paths change.
