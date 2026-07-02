Canvas-jscreen Native Bruno Collection
======================================

Use this folder as a native Bruno collection when testing the
`lab-order-workflow-example` plugin.

Why this exists:

- the repo also contains OpenCollection YAML files under
  `/Users/fahad/Documents/Dev/canvas-plugin-lab/bruno`
- the Canvas logs showed `missing_required_headers`, which indicates Bruno did
  not actually send the runtime HMAC headers
- the native `.bru` request format is the safer path for request-time HMAC
  header injection

Requests included:

- `lab-order-workflow-example-orders.bru`
- `lab-order-workflow-example-orders-create-note.bru`

Expected Bruno environment variables:

- `CANVAS_BASE_URL`
- `HMAC_CLIENT_ID`
- `HMAC_SHARED_SECRET`
- `EXTERNAL_CHECKOUT_ID`
- `CANVAS_PATIENT_ID`
- `PATIENT_FIRST_NAME`
- `PATIENT_LAST_NAME`
- `PATIENT_DOB`
- `NOTE_UUID` for the existing-note request
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

Important signing detail:

- the request URL uses the outer plugin-IO path
- the HMAC canonical path remains `/orders`
