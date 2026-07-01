# Lab Order Workflow Example Plugin Spec

Canonical spec: [docs/specs/lab-order-workflow-example/plugin-spec.md](/Users/fahad/Documents/Dev/canvas-plugin-lab/docs/specs/lab-order-workflow-example/plugin-spec.md)

This plugin is a teaching example for the JScreen/Phytest-style Canvas
lab-order workflow:

- accept structured checkout data through a custom endpoint
- create tracked example workflow state
- move the example into `needs_review` or `ready_to_send`
- listen for the related Canvas lab order to become `sent`
- stop at the Canvas-side boundary

Out of scope:

- real shipment release
- Clarity LIMS integration
- DNA Genotek integration
- consent/document storage
- questionnaire syncing
