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

The request uses a simplified genetic-screening payload with patient identity,
screening type, test code, and whether manual review is required. It accepts
either:

- `note_uuid` for an existing Canvas note
- `note_creation` so the plugin can create a dedicated review note

When `note_creation` is used, the caller supplies note-type identity by
`note_type_system` and/or `note_type_code`. The plugin resolves the active
Canvas note type internally and rejects missing or ambiguous matches with a
`400` response. Providing both fields is the recommended request shape.

The request also requires real `test_order_codes` and defaults `lab_partner` to
`Generic Lab` when omitted.

The intake endpoint requires HMAC-signed server-to-server headers:

- `X-Canvas-Client-Id`
- `X-Canvas-Timestamp`
- `X-Canvas-Nonce`
- `X-Canvas-Content-SHA256`
- `X-Canvas-Signature`

The plugin reads its auth config from Canvas plugin secrets:

- `simpleapi-hmac-client-id`
- `simpleapi-hmac-shared-secret`
- `simpleapi-hmac-previous-shared-secret` (optional)
- `simpleapi-hmac-allowed-skew-seconds` (optional, default `300`)
- `simpleapi-hmac-replay-window-seconds` (optional, default `600`)

Replay protection is enforced with a plugin-backed nonce store. The plugin no
longer exposes a public/debug read endpoint for workflow inspection.

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
- Bruno request examples live under `/Users/fahad/Documents/Dev/canvas-plugin-lab/bruno`
  and are designed to use environment files plus request-time HMAC signing.
- The manifest controls which handlers Canvas loads; update
  `CANVAS_MANIFEST.json` if handler class paths change.
