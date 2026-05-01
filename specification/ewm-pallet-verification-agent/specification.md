# Specification: ewm-pallet-verification-agent

> **Solution Type:** Joule Agent (Joule Skills & Actions)  
> **Guidelines**: Read [guidelines.md](../guidelines.md) before executing ANY tasks below.

---

## Overview

Build the **EWM Pallet Verification Joule Agent** as a set of SAP Joule Skills and Joule Actions authored in SAP Build and deployed via SAP AI Launchpad. The agent enables warehouse workers and supervisors to verify outbound pallet HU labels against live SAP EWM data, and remediate discrepancies by reversing incorrect picks and creating new warehouse tasks â all through the Joule conversational UI.

**API specs available in** `specification/ewm-pallet-verification-agent/api-specs/`:
- `warehouse-outbound-delivery-order.json` â ORD ID `sap.s4:apiResource:WAREHOUSEOUTBDELIVERYORDER_0001:v1`
- `handling-unit.json` â ORD ID `sap.s4:apiResource:OP_HANDLINGUNIT_0001:v1`
- `outbound-delivery.json` â ORD ID `sap.s4:apiResource:OP_API_OUTBOUND_DELIVERY_SRV_0002:v2` *(signature expired; use ORD ID reference)*
- `warehouse-order-task.json` â ORD ID `sap.s4:apiResource:OP_WAREHOUSEORDER_0001:v1` *(signature expired; use ORD ID reference)*

---

## 1. Prerequisites & Environment Setup

- [ ] Verify SAP BTP subaccount has **Joule** entitlement and **SAP AI Launchpad** service instance configured
- [ ] Verify **SAP Build** is accessible and connected to the BTP subaccount for skill authoring
- [ ] Confirm **SAP AI Core** is provisioned with a multimodal model deployment (e.g. `gpt-4o` or equivalent via SAP Generative AI Hub) capable of image input
- [ ] Confirm connectivity from BTP to SAP S/4HANA Cloud Private Edition (EWM) â destination configured in BTP Connectivity service named `M20CLNT100`
- [ ] Verify OAuth2 client credentials for EWM OData API access are stored as BTP destination secrets
- [ ] Confirm the following EWM OData service URLs are reachable from BTP:
  - Warehouse Outbound Delivery Order: `/sap/opu/odata4/sap/api_warehouse_outbound_delivery_order/srvd_a2x/sap/warehouseoutbdeliveryorder/0001/`
  - Handling Unit: `/sap/opu/odata4/sap/op_api_handlingunit/srvd_a2x/sap/handlingunit/0001/`
  - Warehouse Order & Task: `/sap/opu/odata4/sap/op_api_warehouse_order/srvd_a2x/sap/warehouseorder/0001/`

---

## 2. Joule Actions â EWM OData Integrations

Each Action is configured in SAP Build as an OData/REST connector. Reference `api-specs/warehouse-outbound-delivery-order.json` and `api-specs/handling-unit.json` for field names and request/response schemas.

### 2a. Action: GetOutboundDeliveryOrder

- [ ] Create Joule Action `GetOutboundDeliveryOrder` in SAP Build
- [ ] Set HTTP method: `GET`
- [ ] Set endpoint: `GET /WhseOutboundDeliveryOrderHead/{EWMOutboundDeliveryOrder}` from ORD ID `sap.s4:apiResource:WAREHOUSEOUTBDELIVERYORDER_0001:v1`
- [ ] Configure input parameter: `EWMOutboundDeliveryOrder` (string, required) â the outbound delivery order number
- [ ] Configure `$expand=_WhseOutbDeliveryOrderItem` to retrieve line items and their assigned HU references in a single call
- [ ] Map output fields: `EWMOutboundDeliveryOrder`, `GoodsIssueStatus`, `OverallBlockingStatus`, item list with `EWMOutboundDeliveryOrderItem`, `HandlingUnitExternalID`, `Product`, `ActualDeliveryQuantity`
- [ ] Set destination: `M20CLNT100`; authentication: OAuth2 client credentials from BTP destination
- [ ] Add error handling: surface EWM error message in Joule response when HTTP 4xx/5xx is returned

### 2b. Action: GetHandlingUnitDetails

- [ ] Create Joule Action `GetHandlingUnitDetails` in SAP Build
- [ ] Set HTTP method: `GET`
- [ ] Set endpoint: `GET /HandlingUnit/{HandlingUnitExternalID}/{Warehouse}` from ORD ID `sap.s4:apiResource:OP_HANDLINGUNIT_0001:v1`
- [ ] Configure input parameters: `HandlingUnitExternalID` (string, required), `Warehouse` (string, required)
- [ ] Configure `$expand=_HandlingUnitItem,_HandlingUnitAlternativeID,_HandlingUnitReferenceDoc` to retrieve HU contents and reference documents
- [ ] Map output fields: `HandlingUnitExternalID`, `Warehouse`, `HandlingUnitType`, item sub-list with `Product`, `Batch`, `StockItemUUID`; reference doc sub-list with `HandlingUnitReferenceDocument`
- [ ] Set destination: `M20CLNT100`; authentication: OAuth2 client credentials

### 2c. Action: LookUpHUByBarcode

- [ ] Create Joule Action `LookUpHUByBarcode` in SAP Build
- [ ] Set HTTP method: `GET`
- [ ] Set endpoint: `GET /HandlingUnitAlternativeID` from ORD ID `sap.s4:apiResource:OP_HANDLINGUNIT_0001:v1`
- [ ] Configure input parameter: `scannedBarcode` (string, required)
- [ ] Apply OData filter: `$filter=EWMHndlgUnitAltvIDType eq 'SSCC' and AlternativeHandlingUnitID eq '{scannedBarcode}'`
- [ ] Configure `$expand=_HandlingUnit/_HandlingUnitReferenceDoc` to resolve delivery assignment from barcode
- [ ] Map output fields: resolved `HandlingUnitExternalID`, `Warehouse`, and linked `HandlingUnitReferenceDocument` (outbound delivery reference)
- [ ] Set destination: `M20CLNT100`; authentication: OAuth2 client credentials

### 2d. Action: BlockDelivery

- [ ] Create Joule Action `BlockDelivery` in SAP Build
- [ ] Set HTTP method: `PATCH`
- [ ] Set endpoint: `PATCH /WhseOutboundDeliveryOrderHead/{EWMOutboundDeliveryOrder}` from ORD ID `sap.s4:apiResource:WAREHOUSEOUTBDELIVERYORDER_0001:v1`
- [ ] Configure input parameters: `EWMOutboundDeliveryOrder` (string, required), `blockingReason` (string, required, default `"HU_MISMATCH"`)
- [ ] Set request body: `{ "OverallBlockingStatus": "B", "BlockingReason": "{blockingReason}" }`
- [ ] Mark as **high-risk write action** â configure Joule to require explicit worker/supervisor confirmation prompt before invocation
- [ ] Set destination: `M20CLNT100`; authentication: OAuth2 client credentials

### 2e. Action: CancelPickingTask

- [ ] Create Joule Action `CancelPickingTask` in SAP Build
- [ ] Set HTTP method: `POST` (cancel action endpoint on warehouse task)
- [ ] Set endpoint using ORD ID `sap.s4:apiResource:OP_WAREHOUSEORDER_0001:v1` â warehouse task cancellation action
- [ ] Configure input parameters: `WarehouseNumber` (string), `WarehouseOrder` (string), `WarehouseTask` (string) â all required
- [ ] Mark as **high-risk write action** â require confirmation before invocation
- [ ] Set destination: `M20CLNT100`; authentication: OAuth2 client credentials

### 2f. Action: ReverseWarehouseTask

- [ ] Create Joule Action `ReverseWarehouseTask` in SAP Build
- [ ] Set HTTP method: `POST` (reversal action on warehouse task)
- [ ] Set endpoint using ORD ID `sap.s4:apiResource:OP_WAREHOUSEORDER_0001:v1` â warehouse task reversal
- [ ] Configure input parameters: `WarehouseNumber` (string), `WarehouseOrder` (string), `WarehouseTask` (string) â all required
- [ ] Map output: confirmation of reversal, source storage bin the HU was returned to
- [ ] Mark as **high-risk write action** â require confirmation before invocation
- [ ] Set destination: `M20CLNT100`; authentication: OAuth2 client credentials

### 2g. Action: CreateWarehouseTask

- [ ] Create Joule Action `CreateWarehouseTask` in SAP Build
- [ ] Set HTTP method: `POST` (create warehouse task on warehouse order)
- [ ] Set endpoint using ORD ID `sap.s4:apiResource:OP_WAREHOUSEORDER_0001:v1` â warehouse task creation
- [ ] Configure input parameters: `WarehouseNumber` (string), `WarehouseOrder` (string), `HandlingUnitExternalID` (string), `DestinationStorageBin` (string) â all required
- [ ] Map output: new `WarehouseTask` number, source bin, destination bin
- [ ] Mark as **high-risk write action** â require confirmation before invocation
- [ ] Set destination: `M20CLNT100`; authentication: OAuth2 client credentials

---

## 3. Joule Skills â Conversational Orchestration

### 3a. Skill: VerifyPalletLoading (Primary)

- [ ] Create Joule Skill `VerifyPalletLoading` in SAP Build
- [ ] Set skill description (used for intent routing): *"Verify the HU labels on a pallet against the SAP EWM outbound delivery before loading. Accepts a pallet photo and delivery number or HU barcode."*
- [ ] Define skill trigger phrases: *"verify pallet"*, *"check pallet labels"*, *"scan pallet"*, *"pallet verification"*, *"loading check"*
- [ ] Define skill input slots:
  - `deliveryNumber` (optional string) â outbound delivery order number; filled by worker or resolved from photo
  - `palletPhoto` (required image/file) â photo of the pallet to verify; collected via Joule file upload prompt
  - `warehouseNumber` (required string) â EWM warehouse number; can default from user profile
- [ ] **Step 1 â Photo Intake (Milestone M1):**
  - [ ] Prompt worker: *"Please upload or take a photo of the pallet you want to verify."*
  - [ ] Validate image received (non-empty, supported format: JPEG/PNG)
  - [ ] Emit structured log: `M1.achieved: pallet photo ingested successfully from channel=joule, delivery={deliveryNumber}`
  - [ ] On failure: emit `M1.missed: pallet photo ingestion failed â invalid format or missing image`; prompt retry
- [ ] **Step 2 â AI Vision Analysis (Milestone M2):**
  - [ ] Invoke SAP AI Core multimodal model step with the photo and prompt: *"Identify all handling unit labels visible on this pallet. For each label: (1) state if it is physically present and readable, (2) extract the SSCC barcode or HU ID text. Return results as a JSON array."*
  - [ ] Parse model response; extract `detectedHUs` list with `huId`, `readable` (boolean), `confidence` (float)
  - [ ] If any label's `confidence < 0.75`: emit `M2.missed: HU label detection confidence below threshold â retake requested`; send worker prompt: *"Photo quality is too low for reliable verification. Please retake with better lighting or a closer angle."*; loop back to Step 1
  - [ ] Emit `M2.achieved: HU labels detected â count={n}, confidence={avg_score}, low_readability_flags={k}`
- [ ] **Step 3 â Delivery Resolution (if no deliveryNumber provided):**
  - [ ] If `deliveryNumber` is empty and at least one `detectedHUs[].huId` is present: invoke sub-skill `LookUpHUByBarcode` with first readable HU barcode
  - [ ] Populate `deliveryNumber` from sub-skill result; if unresolvable: prompt worker to enter delivery number manually
- [ ] **Step 4 â EWM Data Fetch (Milestone M3):**
  - [ ] Invoke Action `GetOutboundDeliveryOrder` with `deliveryNumber`
  - [ ] Store `expectedHUs` list from delivery item `HandlingUnitExternalID` fields
  - [ ] Emit `M3.achieved: EWM delivery data fetched â delivery={deliveryNumber}, expected_HU_count={n}`
  - [ ] On Action failure: emit `M3.missed: EWM delivery data fetch failed â delivery={deliveryNumber}, error={message}`; surface error to worker; halt flow
- [ ] **Step 5 â HU Matching (Milestone M4):**
  - [ ] Invoke sub-skill `GenerateVerificationReport` with `detectedHUs` and `expectedHUs`
  - [ ] Receive `matchResult`: `matched`, `missing`, `extra`, `unreadable` lists
  - [ ] Emit `M4.achieved: HU matching completed â matched={n}, missing={m}, extra={e}, unreadable={u}`
  - [ ] On error: emit `M4.missed: HU matching could not be completed â insufficient data`
- [ ] **Step 6 â Report & Blocking (Milestone M5):**
  - [ ] Invoke sub-skill `GenerateVerificationReport` to format the final pass/fail report card
  - [ ] Present report to worker in Joule chat with overall status (PASS / FAIL), matched HU count, and itemised discrepancy list
  - [ ] If `matchResult.extra` or `matchResult.missing` is non-empty AND confidence > 0.75: invoke Action `BlockDelivery` (with confirmation prompt) and set `deliveryBlocked = true`
  - [ ] Emit `M5.achieved: verification report delivered â status={PASS|FAIL}, delivery_blocked={deliveryBlocked}`
  - [ ] On report generation failure: emit `M5.missed: verification report generation failed â worker notified to escalate`
  - [ ] If discrepancies exist: present option to worker: *"Do you want to remediate incorrect HUs now?"* â if confirmed, invoke sub-skill `RemediateIncorrectHU`

### 3b. Skill: LookUpHUByBarcode (Sub-Skill)

- [ ] Create Joule Skill `LookUpHUByBarcode` in SAP Build
- [ ] Set as a callable sub-skill (not directly user-triggered)
- [ ] Define input: `scannedBarcode` (string, required)
- [ ] Invoke Action `LookUpHUByBarcode` with the barcode
- [ ] Return resolved `deliveryNumber` and `warehouseNumber` to the calling skill
- [ ] On not-found: return empty result; calling skill falls back to manual delivery number prompt

### 3c. Skill: GenerateVerificationReport (Sub-Skill)

- [ ] Create Joule Skill `GenerateVerificationReport` in SAP Build
- [ ] Set as a callable sub-skill
- [ ] Define inputs: `detectedHUs` (array), `expectedHUs` (array)
- [ ] Cross-reference lists: match by HU ID / SSCC; classify each into `matched`, `missing` (in expected but not detected), `extra` (detected but not in expected), `unreadable` (detected but `readable=false`)
- [ ] Return structured `matchResult` with the four lists and overall `status` (PASS if `missing` and `extra` are both empty and `unreadable` is empty, else FAIL)
- [ ] Format a human-readable report card for presentation in Joule chat:
  - Header: delivery number, warehouse, overall status (â PASS / â FAIL)
  - Table: each expected HU with match status
  - Footer: action recommendations for discrepant HUs

### 3d. Skill: RemediateIncorrectHU (Sub-Skill)

- [ ] Create Joule Skill `RemediateIncorrectHU` in SAP Build
- [ ] Set as a callable sub-skill and also directly user-triggerable: *"remediate incorrect HU"*, *"reverse wrong pick"*, *"fix wrong pallet"*
- [ ] Define inputs: `deliveryNumber` (string), `warehouseNumber` (string), `incorrectHUIds` (string array), `correctHUIds` (string array â the expected HU IDs that should replace them)
- [ ] **Step 1 â Confirm with worker/supervisor:**
  - [ ] Present confirmation prompt: *"I will cancel the picking of {incorrectHUIds}, reverse the warehouse tasks, and create new tasks to pick {correctHUIds}. Do you confirm?"*
  - [ ] If not confirmed: abort and inform worker; no write Actions are invoked
- [ ] **Step 2 â Cancel picking for each incorrect HU (Milestone M6, partial):**
  - [ ] For each `incorrectHUId`: resolve warehouse task IDs via `GetOutboundDeliveryOrder` (or previously fetched data)
  - [ ] Invoke Action `CancelPickingTask` for each task
- [ ] **Step 3 â Reverse warehouse tasks:**
  - [ ] Invoke Action `ReverseWarehouseTask` for each cancelled task; collect storage bins HUs were returned to
- [ ] **Step 4 â Create new warehouse tasks:**
  - [ ] Invoke Action `CreateWarehouseTask` for each `correctHUId` on the delivery
  - [ ] Collect new task numbers and destination bins
- [ ] **Step 5 â Report remediation outcome (Milestone M6, complete):**
  - [ ] Emit `M6.achieved: HU remediation completed â reversed_tasks={n}, created_tasks={n}, delivery={deliveryNumber}`
  - [ ] On any step failure: emit `M6.missed: HU remediation partially failed â failed_reversals={n}, failed_creations={n}, delivery={deliveryNumber}, worker notified to escalate`
  - [ ] Present summary to worker: which HUs were returned, new task numbers and pick locations for correct HUs

### 3e. Skill: SupervisorOverride (Sub-Skill)

- [ ] Create Joule Skill `SupervisorOverride` in SAP Build
- [ ] Set trigger phrases: *"release delivery block"*, *"override delivery block"*, *"supervisor approval"*
- [ ] Define input: `deliveryNumber` (string, required)
- [ ] Verify caller has supervisor role in Joule (role-based access check via SAP BTP authorization)
- [ ] Present discrepancy summary for the delivery (fetched via `GetOutboundDeliveryOrder`)
- [ ] Require supervisor to confirm: *"I confirm I have reviewed the discrepancy and approve releasing the block on delivery {deliveryNumber}."*
- [ ] Invoke Action: `PATCH /WhseOutboundDeliveryOrderHead/{EWMOutboundDeliveryOrder}` with `OverallBlockingStatus: ""` to clear the block
- [ ] Log override with supervisor user ID, delivery number, and timestamp
- [ ] Return confirmation message to supervisor

---

## 4. Joule Agent Configuration

- [ ] Register all Skills (`VerifyPalletLoading`, `LookUpHUByBarcode`, `GenerateVerificationReport`, `RemediateIncorrectHU`, `SupervisorOverride`) under a single Joule Agent definition in SAP AI Launchpad
- [ ] Set agent display name: *"EWM Pallet Verification Agent"*
- [ ] Set agent description: *"Verifies pallet HU labels against SAP EWM outbound delivery data using AI photo analysis, and remediates discrepancies by reversing incorrect picks and creating replacement warehouse tasks."*
- [ ] Configure agent scope: accessible to roles `WarehouseOperator` and `WarehouseSupervisor` in the BTP subaccount
- [ ] Configure multimodal model binding: bind the vision-capable model deployment from SAP AI Core to the `VerifyPalletLoading` skill's AI step
- [ ] Set model input constraints: max image size 10 MB; accepted MIME types `image/jpeg`, `image/png`
- [ ] Configure photo confidence threshold constant: `VISION_CONFIDENCE_THRESHOLD = 0.75` (configurable in skill parameters)
- [ ] Enable Joule embedded surface in SAP S/4HANA Fiori launchpad and SAP Mobile Start

---

## 5. Skill-Level Guardrails

- [ ] Confirm `BlockDelivery`, `CancelPickingTask`, `ReverseWarehouseTask`, `CreateWarehouseTask` Actions all have Joule confirmation prompts enabled (user must explicitly confirm before the Action fires)
- [ ] Confirm that write Actions are **never** invoked when `confidence < VISION_CONFIDENCE_THRESHOLD`
- [ ] Confirm `SupervisorOverride` skill enforces role check before proceeding â unauthorised callers receive: *"You do not have permission to release delivery blocks."*
- [ ] Confirm EWM API error responses are caught at Action level and surface a human-readable message in Joule rather than a raw HTTP error
- [ ] Confirm all 6 milestone log statements (M1âM6, achieved + missed variants) are emitted at the correct skill steps

---

## 6. Testing

- [ ] **Unit test â GetOutboundDeliveryOrder Action:** invoke Action with a test delivery number against the EWM sandbox; verify `WhseOutboundDeliveryOrderHead` header and item list are returned
- [ ] **Unit test â GetHandlingUnitDetails Action:** invoke with a known HU ID and warehouse; verify HU item list and reference docs are returned
- [ ] **Unit test â LookUpHUByBarcode Action:** invoke with a known SSCC barcode; verify resolved delivery number is returned
- [ ] **Unit test â BlockDelivery Action:** invoke in sandbox; verify `OverallBlockingStatus` is set to `"B"` on the delivery
- [ ] **Unit test â CancelPickingTask Action:** invoke with test task IDs in sandbox; verify task status changes to cancelled
- [ ] **Unit test â ReverseWarehouseTask Action:** invoke in sandbox; verify HU storage bin reverts to original location
- [ ] **Unit test â CreateWarehouseTask Action:** invoke in sandbox; verify new task is created and returns task number + bin
- [ ] **Skill test â VerifyPalletLoading (pass scenario):** submit a clear pallet photo with all correct HUs; verify PASS report is returned and no blocking Action fires
- [ ] **Skill test â VerifyPalletLoading (fail + block scenario):** submit a photo with a wrong HU; verify FAIL report, confirm `BlockDelivery` Action is triggered after confirmation prompt
- [ ] **Skill test â VerifyPalletLoading (low-confidence scenario):** submit a blurred or low-resolution photo; verify retake prompt is presented and no write Actions fire
- [ ] **Skill test â RemediateIncorrectHU:** trigger sub-skill with a mismatched HU; verify cancel â reverse â create sequence fires in order; verify M6 log is emitted
- [ ] **Skill test â SupervisorOverride (authorised):** invoke with a supervisor role user; verify delivery block is released
- [ ] **Skill test â SupervisorOverride (unauthorised):** invoke with a non-supervisor user; verify access denial message and no Action fires
- [ ] **End-to-end test:** full flow from photo upload â EWM data fetch â discrepancy detected â block applied â supervisor override; verify all M1âM6 milestones emit `achieved` logs
- [ ] Verify all 6 milestone log statements appear in SAP AI Launchpad observability / Application Logging output

---

## 7. Deployment

- [ ] Invoke `setup-solution` skill to create `solution.yaml` and `asset.yaml` for the Joule Agent asset
- [ ] Package all Skill and Action definitions from SAP Build as an exportable transport
- [ ] Configure BTP destination `M20CLNT100` with EWM system URL, OAuth2 client ID/secret, and `sap-client` header
- [ ] Deploy to SAP AI Launchpad â Dev environment first; run unit and skill tests against EWM sandbox
- [ ] Promote to Production after test sign-off; validate connectivity to EWM production client
- [ ] Validate agent is discoverable in Joule on the SAP S/4HANA Fiori launchpad
- [ ] Confirm all write Action audit logs are flowing to BTP Application Logging / SAP Cloud Logging service
