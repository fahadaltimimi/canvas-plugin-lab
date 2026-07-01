# Lab Order Workflow Example Plugin Spec

Canonical spec: `../../docs/specs/lab-order-workflow-example/plugin-spec.md`

This plugin is a teaching example for the JScreen/Phytest-style Canvas
lab-order workflow:

- accept structured checkout data through a custom endpoint
- require either `note_uuid` or `note_creation`, plus real `test_order_codes`
- default `lab_partner` to `Generic Lab` on the current instance unless
  explicitly overridden
- optionally create a dedicated review note for purchase-flow intake
- originate a real Canvas lab-order command on the resolved Canvas note
- expose a temporary read endpoint for workflow-state inspection
- create tracked workflow state
- backfill the real Canvas lab-order ID from later order events
- move the example into `needs_review` or `ready_to_send`
- listen for the related Canvas lab order to become `sent`
- stop at the Canvas-side boundary

Out of scope:

- real shipment release
- Clarity LIMS integration
- DNA Genotek integration
- consent/document storage
- questionnaire syncing
