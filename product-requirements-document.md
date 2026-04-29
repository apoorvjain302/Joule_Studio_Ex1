# Product Requirements Document (PRD)

**Title:** EWM Pallet Verification Agent  
**Date:** 2026-04-29  
**Owner:** Warehouse Operations / Supply Chain IT  
**Solution Category:** AI Agent

---

## Product Purpose & Value Proposition

**Elevator Pitch:**  
Warehouse workers loading pallets for outbound shipments have no automated way to verify that every handling unit (HU) belongs to the intended delivery and that all labels are present, readable, and correct. This AI agent accepts a pallet photo from any device, reads the EWM backend in real time, and delivers a pass/fail verification report in seconds — preventing mislabelled or wrong-goods shipments before they leave the dock.

**Business Need:**  
Manual pallet loading checks are error-prone and slow. Workers rely on visual inspection and handheld scanning with no cross-check against the live EWM delivery record. Errors — wrong HUs, missing or damaged labels — are typically discovered only after shipment, leading to costly returns, delivery disputes, and customer dissatisfaction.

**Expected Value:**  
- Reduction in wrong-goods and mislabelling incidents at goods issue.
- Faster loading verification replacing time-consuming manual HU-by-HU scanning.
- Improved outbound delivery accuracy and customer SLA compliance.

**Product Objectives (Prioritized):**
1. Detect all HU labels on a pallet photo and validate them against the live EWM outbound delivery record.
2. Alert the warehouse worker instantly with a structured pass/fail report and actionable details on discrepancies.
3. Block the EWM outbound delivery from confirmation when critical mismatches are found, preventing accidental goods issue.
4. Support all common photo-capture modalities — fixed dock camera, handheld scanner, mobile device, and web upload — with no hardware changes required.

---

## User Profiles & Personas

### Primary Persona: Marco — Warehouse Operator

Marco is a 34-year-old warehouse operator working the outbound loading dock on day and afternoon shifts. He operates a handheld barcode scanner and uses a shared tablet for system interactions. His daily routine includes picking, packing, and confirming pallets before truck loading. He is comfortable with scanning-based workflows but is not technically minded when it comes to software. His biggest frustration is discovering a wrong HU or missing label only after the truck has been loaded, requiring rework. He needs a fast, clear signal — green means go, red means stop and fix.

### Secondary Persona: Lena — Warehouse Supervisor

Lena is a 42-year-old warehouse shift supervisor responsible for outbound delivery accuracy and team productivity. She monitors loading progress via the EWM monitor and steps in when operators flag problems. She needs visibility into which deliveries have failed verification and why, and the ability to override a blocked delivery when she has reviewed and approved the exception.

### Other User Types

- **Shipping Coordinator**: Monitors delivery readiness; needs to know whether all pallets for a shipment have passed verification before releasing for goods issue.

---

## User Goals & Tasks

### For Marco (Warehouse Operator):

**Goals:**
- Confirm before loading that all HUs on a pallet belong to the correct outbound delivery.
- Ensure every HU label is physically present, undamaged, readable, and matches EWM data.
- Receive a clear, immediate result without navigating complex EWM screens.

**Key Tasks:**
- Capture or upload a pallet photo via handheld, fixed camera, mobile, or web.
- Provide or confirm the outbound delivery number (or let the agent resolve it from the photo).
- Review the verification report and act on any flagged issues before loading.

### For Lena (Warehouse Supervisor):

**Goals:**
- Review blocked deliveries and decide whether to approve exceptions.
- Monitor the verification status across active outbound deliveries on the shift.

**Key Tasks:**
- View a summary of failed verifications with root cause details.
- Override a delivery block after manual inspection and approval.

---

## Goals and Non-Goals

### Goals (In Scope)

- Accept pallet photos from fixed cameras, handheld scanners, mobile devices, and web uploads.
- Use a multimodal LLM (vision model) to detect HU labels, assess physical presence, readability, and extract barcode/text data.
- Fetch outbound delivery and HU data in real time from SAP EWM (S/4HANA Cloud Private Edition) via OData APIs.
- Resolve the relevant delivery from either a user-provided delivery number or by matching detected HU barcodes to EWM records.
- Cross-reference detected HUs against expected HUs on the delivery and report missing, extra, or unreadable HUs.
- Generate a structured pass/fail verification report presented to the worker.
- Block the EWM outbound delivery when critical mismatches are found; support supervisor override.
- Instrument all business steps with structured log statements for observability.

### Non-Goals (Out of Scope)

- Inbound delivery or goods receipt verification (outbound only).
- Automatic goods issue posting — confirmation remains a manual step by the shipping coordinator.
- Full goods damage assessment or quality inspection beyond label and HU identity verification.
- Integration with transport management or carrier systems.
- Custom EWM configuration or label template changes.

---

## Requirements

### Must-Have Requirements

**REQ-01: Multi-Channel Photo Ingestion**

- **Problem to Solve**: Workers use different devices; a single rigid input method would exclude large parts of the workforce.
- **User Story**: As a warehouse operator, I need to submit a pallet photo from my handheld scanner, mobile device, fixed dock camera, or web browser so that I can verify the pallet regardless of the device available at my workstation.
- **Acceptance Criteria**:
  - Given a photo is submitted via any supported channel, when the agent receives it, then the image is accepted and processed without errors.
- **Maps to Objective**: 4
- **Priority Rank**: 1

**REQ-02: AI Vision-Based HU Label Detection**

- **Problem to Solve**: Labels on a pallet must be physically present and readable; manual visual checks are unreliable.
- **User Story**: As a warehouse operator, I need the agent to detect all visible HU labels in the photo so that I can confirm every HU is correctly labelled before loading.
- **Acceptance Criteria**:
  - Given a pallet photo, when the agent processes it, then it identifies the count and location of HU labels present, and flags any that appear missing, damaged, or unreadable.
- **Maps to Objective**: 1
- **Priority Rank**: 2

**REQ-03: Label Content Extraction and EWM Data Comparison**

- **Problem to Solve**: Workers cannot manually cross-check every barcode on a multi-HU pallet against the EWM delivery record quickly and accurately.
- **User Story**: As a warehouse operator, I need the agent to read barcode/text from each label and compare it to the EWM delivery data so that I know whether the correct goods are loaded.
- **Acceptance Criteria**:
  - Given label barcodes are extracted from the photo, when compared to the EWM delivery HU list, then any HU ID present on the pallet but not on the delivery (or vice versa) is flagged as a discrepancy.
- **Maps to Objective**: 1
- **Priority Rank**: 3

**REQ-04: Live EWM Delivery and HU Data Retrieval**

- **Problem to Solve**: Verification must be against live, authoritative data — not cached or static — because deliveries can be modified up to loading time.
- **User Story**: As a warehouse operator, I need the agent to fetch the current outbound delivery and HU assignments from EWM in real time so that my verification is accurate at the moment of loading.
- **Acceptance Criteria**:
  - Given a delivery number or a resolved HU barcode, when the agent calls the EWM OData API, then it retrieves the current delivery header, line items, and assigned HU list.
- **Maps to Objective**: 1
- **Priority Rank**: 4

**REQ-05: Delivery Resolution from HU Barcode**

- **Problem to Solve**: Workers may not always know or have the delivery number at hand; they should be able to initiate verification by scanning any HU on the pallet.
- **User Story**: As a warehouse operator, I need the agent to identify the outbound delivery by reading an HU barcode from the photo so that I can start verification without manually entering a delivery number.
- **Acceptance Criteria**:
  - Given an HU barcode is extracted from the photo and no delivery number is provided, when the agent queries EWM, then it resolves and returns the associated outbound delivery.
- **Maps to Objective**: 1, 4
- **Priority Rank**: 5

**REQ-06: Structured Pass/Fail Verification Report**

- **Problem to Solve**: Workers need an immediate, unambiguous result they can act on without interpreting raw data.
- **User Story**: As a warehouse operator, I need a clear pass/fail report after each verification so that I know whether to proceed with loading or stop and resolve issues.
- **Acceptance Criteria**:
  - Given verification is complete, when results are returned to the worker, then the report includes overall pass/fail status, a list of detected HUs with match status, and specific discrepancy details (missing HU, extra HU, unreadable label).
- **Maps to Objective**: 2
- **Priority Rank**: 6

**REQ-07: Delivery Blocking on Critical Discrepancy**

- **Problem to Solve**: Without a system block, a worker under time pressure may proceed with loading despite flagged issues.
- **User Story**: As a warehouse supervisor, I need the agent to block the EWM delivery when a critical mismatch is found so that accidental goods issue of incorrect shipments is prevented.
- **Acceptance Criteria**:
  - Given a critical discrepancy is detected (wrong HU on pallet or unreadable label on all HUs), when the agent calls the EWM API, then a blocking reason is set on the outbound delivery and the worker is informed.
- **Maps to Objective**: 3
- **Priority Rank**: 7

**REQ-08: Low-Confidence Retry Prompt**

- **Problem to Solve**: Poor photo quality (blur, low light, occlusion) reduces AI detection accuracy and could produce false results.
- **User Story**: As a warehouse operator, I need the agent to tell me when the photo quality is too low for reliable verification so that I can retake the photo before acting on the result.
- **Acceptance Criteria**:
  - Given the vision model returns a confidence score below threshold, when results are returned, then the agent prompts the worker to retake the photo rather than delivering a potentially inaccurate result.
- **Maps to Objective**: 1, 2
- **Priority Rank**: 8

---

## Solution Architecture

**Architecture Overview:**  
A Python AI agent deployed on SAP App Foundation, communicating over the A2A protocol. The agent orchestrates a multimodal LLM for vision tasks and calls SAP EWM OData APIs directly for live data. Workers interact via any supported front-end channel.

**Key Components:**

- **AI Agent (Python, A2A)** — core orchestration logic; manages the verification workflow, tool calls, and report generation.
- **Multimodal LLM (Vision Model)** — performs HU label detection, readability assessment, and barcode/text extraction from pallet photos.
- **SAP EWM OData Integration Layer** — set of agent tools wrapping EWM OData APIs for delivery and HU data retrieval and delivery status updates.
- **Input Channel Adapter** — normalises photo inputs from fixed camera, handheld scanner, mobile UI, and web upload into a uniform format for the agent.

**Integration Points:**

- **SAP S/4HANA Cloud Private Edition (EWM)** — read outbound delivery order and HU details; write delivery block; accessed via OData APIs (`OP_API_OUTBOUND_DELIVERY_SRV_0002`, `OP_HANDLINGUNIT_0001`, `WAREHOUSEOUTBDELIVERYORDER_0001`).

**Deployment Environments:**

- **Dev/QA**: Connected to EWM sandbox/test client; photo submissions use synthetic test images.
- **Production**: Connected to EWM production client; all blocking actions are logged for audit.

### Agent Extensibility & Instrumentation

**Agent Extensibility:**
- The agent exposes extension points for adding new verification checks (e.g., expiry date validation, hazmat label compliance) without modifying the core verification flow.
- Supervisor override logic is exposed as a distinct, replaceable tool so it can be adapted to different approval workflows.
- Tool definitions follow the A2A protocol, allowing future integration of additional EWM capabilities (e.g., writing proof-of-delivery notes) without rewriting agent logic.

**Business Step Instrumentation:**
- Every milestone defined below must emit a structured log statement on achievement and on miss/skip.
- Log format: `[MILESTONE_ID].[achieved|missed]: <description>`
- Logs are forwarded to the SAP App Foundation observability pipeline for monitoring and alerting.

### Automation & Agent Behaviour

**Automation Level:** Autonomous agent with human-in-the-loop for blocking overrides.

**Actions the system performs without human approval:**
- Fetching outbound delivery and HU data from EWM.
- Analysing pallet photo and extracting label data.
- Generating and delivering the verification report to the worker.
- Setting a delivery block on EWM when a critical discrepancy is detected.

**Actions that require human review or approval:**
- Releasing a delivery block (supervisor override).
- Proceeding with loading after a partial-confidence result (worker decision).

**Model or engine used:** Multimodal LLM with vision capability (e.g., GPT-4o via SAP Generative AI Hub).

**Knowledge & data sources accessed:**
- SAP EWM (S/4HANA Cloud Private Edition): outbound delivery orders, handling unit master data, label field catalog.

**Tools or connectors invoked:**
- `analyze_pallet_photo` — sends image to vision model; detects labels, assesses readability, extracts barcodes. Read-only.
- `get_outbound_delivery` — reads delivery header, items, and assigned HU list from EWM. Read-only.
- `get_handling_unit_details` — reads HU content, packing material, and delivery assignment from EWM. Read-only.
- `lookup_hu_by_barcode` — resolves HU barcode/SSCC to outbound delivery assignment. Read-only.
- `generate_verification_report` — cross-references detected vs. expected HUs; produces pass/fail report. Read-only.
- `block_delivery` — sets blocking reason on EWM outbound delivery. **Write / high-risk** — triggered only on critical discrepancy.

**Guardrails & fail-safes:**
- `block_delivery` is called only when the vision model confidence exceeds the threshold AND a definitive HU mismatch is confirmed; it is never called on a low-confidence result.
- If EWM API is unreachable, the agent surfaces a clear error message and does not deliver a result, prompting the worker to retry or escalate to the supervisor.
- If photo confidence is below threshold, the agent requests a retake before proceeding.
- All `block_delivery` invocations are logged with delivery number, timestamp, detected discrepancy, and worker ID for audit.

---

## Milestones

### M1: Photo Ingested

- **Description**: Pallet photo received and pre-processed for AI analysis.
- **Achieved when**: Image is received from any input channel and validated (format, minimum resolution).
- **Log on achievement**: `M1.achieved: pallet photo ingested successfully from channel={channel}, image_id={id}`
- **Log on miss**: `M1.missed: pallet photo ingestion failed — invalid format or resolution below threshold`

### M2: HU Labels Detected

- **Description**: AI vision model has identified all visible HU labels on the pallet.
- **Achieved when**: Vision model returns label detection results with confidence above threshold.
- **Log on achievement**: `M2.achieved: HU labels detected — count={n}, confidence={score}, low_readability_flags={k}`
- **Log on miss**: `M2.missed: HU label detection failed or confidence below threshold — retake requested`

### M3: Delivery Data Fetched

- **Description**: Outbound delivery number resolved and full expected HU list retrieved from EWM.
- **Achieved when**: EWM API returns delivery header and complete HU assignment list.
- **Log on achievement**: `M3.achieved: EWM delivery data fetched — delivery={number}, expected_HU_count={n}`
- **Log on miss**: `M3.missed: EWM delivery data fetch failed — delivery={number}, error={message}`

### M4: HU Matching Completed

- **Description**: Detected HUs cross-referenced against expected EWM delivery HUs.
- **Achieved when**: Comparison completes and discrepancy list (if any) is produced.
- **Log on achievement**: `M4.achieved: HU matching completed — matched={n}, missing={m}, extra={e}, unreadable={u}`
- **Log on miss**: `M4.missed: HU matching could not be completed — insufficient label data or delivery data unavailable`

### M5: Verification Report Generated

- **Description**: Structured pass/fail report produced and delivered to the worker; delivery blocked if critical discrepancy found.
- **Achieved when**: Report is returned to the worker AND delivery block is set (if applicable).
- **Log on achievement**: `M5.achieved: verification report delivered — status={PASS|FAIL}, delivery_blocked={true|false}`
- **Log on miss**: `M5.missed: verification report generation failed — worker notified to escalate`

---

## Risks, Assumptions, and Dependencies

### Risks

- **Vision accuracy on challenging conditions**: Poor lighting, motion blur, or label occlusion can reduce detection accuracy. Mitigation: confidence thresholding and retake prompts.
- **EWM API latency**: Real-time OData calls add latency. Mitigation: retry logic, async where possible, and clear timeout error messaging.
- **Delivery blocking misuse**: Incorrect blocks cause operational disruption. Mitigation: supervisor override tool; audit log of all blocking actions.
- **Multi-HU pallet complexity**: Densely packed pallets may obscure individual labels. Mitigation: prompt worker to capture multiple angles when label count detected is lower than expected.

### Assumptions

- SAP S/4HANA Cloud Private Edition (embedded EWM) OData APIs are accessible from the SAP BTP runtime where the agent is deployed.
- A multimodal LLM with vision capabilities is available via SAP Generative AI Hub or equivalent BTP AI service.
- HU labels on pallets contain a machine-readable barcode (GS1-128 / SSCC) that the vision model can extract.
- Warehouse workers operating the agent have been trained on the capture workflow and understand the pass/fail output.

### Dependencies

- SAP S/4HANA Cloud Private Edition EWM OData APIs (`OP_API_OUTBOUND_DELIVERY_SRV_0002`, `OP_HANDLINGUNIT_0001`, `WAREHOUSEOUTBDELIVERYORDER_0001`).
- Multimodal LLM with vision capability accessible via SAP AI Core / Generative AI Hub.
- SAP App Foundation runtime for agent deployment.
- Network connectivity between SAP BTP and the S/4HANA Cloud Private Edition tenant.

---

## Appendix

### Glossary

- **HU (Handling Unit)**: A physical unit of goods with a unique identifier managed in SAP EWM, typically labelled with an SSCC barcode.
- **SSCC (Serial Shipping Container Code)**: GS1-standard barcode used to identify a handling unit.
- **Outbound Delivery**: An SAP EWM/S/4HANA document that records the goods to be shipped to a customer, linked to one or more HUs.
- **Delivery Block**: A status flag on an SAP outbound delivery that prevents goods issue confirmation until cleared.
- **Goods Issue (GI)**: The SAP posting that records the physical departure of goods from the warehouse, reducing stock.
- **A2A Protocol**: Agent-to-Agent communication protocol used by SAP App Foundation agents.

### References

- SAP Help: Warehouse Outbound Delivery Order OData API (`WAREHOUSEOUTBDELIVERYORDER_0001`)
- SAP Help: Handling Unit OData API (`OP_HANDLINGUNIT_0001`)
- SAP Help: Outbound Delivery A2X OData API (`OP_API_OUTBOUND_DELIVERY_SRV_0002`)
- SAP App Foundation Agent Development Guide
- SAP Generative AI Hub — Multimodal Model Documentation
