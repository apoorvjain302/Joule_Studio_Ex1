# EWM Pallet Verification Agent

AI-powered pallet verification agent for SAP Extended Warehouse Management outbound loading

## Business challenge

Warehouse workers loading pallets for outbound deliveries currently have no automated way to confirm that:
1. All handling units (HUs) physically present on a pallet belong to the intended outbound delivery being loaded.
2. Every HU label is physically present, undamaged, readable, and contains the correct data matching the EWM delivery record.

This creates a risk of shipping wrong goods, mislabelled pallets, or incomplete deliveries — errors that are costly to resolve after goods have left the warehouse. The solution must connect to a live SAP EWM backend (S/4HANA Cloud Private Edition) to fetch authoritative delivery and HU data, and support multiple photo-capture modalities (fixed dock camera, handheld scanner, mobile device, and web upload).

## Key Milestones

1. **Photo Ingested** — pallet photo received from any supported input channel and pre-processed for analysis.
2. **HU Labels Detected** — AI vision identifies all HU labels in the image, checks physical presence and readability.
3. **Delivery Data Fetched** — outbound delivery number resolved (user-supplied or inferred from HU barcodes) and full HU list retrieved from EWM via OData API.
4. **HU Matching Completed** — detected HUs cross-referenced against expected HUs on the delivery; discrepancies identified.
5. **Verification Report Generated** — structured report produced; worker alerted with pass/fail status, with delivery blocked if mismatches are found.

## Business Architecture (RBA)

### End-to-End Process

Plan to Fulfill (E2E-217)

### Process Hierarchy

```
Plan to Fulfill (E2E-217)
└── Deliver Product to Fulfill (generic) (MBP-538)
    └── Manage warehouse and inventory (generic) (BPS-348)
        └── Coordinate dock and yard logistics (BA-2940)
```

### Summary

AI-powered pallet photo analysis during EWM outbound loading maps to Plan to Fulfill → Deliver Product to Fulfill → Manage warehouse and inventory (generic), covering dock/yard logistics coordination and HU label verification against outbound delivery documents.

## Fit Gap Analysis

| Requirement (business) | Standard asset(s) found | API ORD ID | MCP Server ORD ID | Gap? | Notes / assumptions |
| ---------------------- | ----------------------- | ---------- | ----------------- | ---- | ------------------- |
| Outbound delivery and HU data retrieval from EWM | SAP S/4HANA Cloud Private Edition — Outbound Warehouse Management (EWM) SC5105 | `sap.s4:apiResource:WAREHOUSEOUTBDELIVERYORDER_0001:v1` | — | No | OData API available; no MCP server; direct API integration required |
| Handling unit detail lookup (HU ID, contents, delivery assignment) | SAP S/4HANA Cloud Private Edition | `sap.s4:apiResource:OP_HANDLINGUNIT_0001:v1` | — | No | OData API available; no MCP server |
| Outbound delivery order read (items, quantities, status) | SAP S/4HANA Cloud Private Edition — Outbound Delivery Management SC6221 | `sap.s4:apiResource:OP_API_OUTBOUND_DELIVERY_SRV_0002:v2` | — | No | OData API available |
| Label template / field catalog lookup for expected label fields | SAP S/4HANA Cloud Private Edition | `sap.s4:apiResource:LABELFIELDCATALOG_0001:v1` | — | No | OData API available for label field definitions |
| AI vision-based detection of HU labels in photo | None | — | — | **Yes** | No standard SAP product covers computer vision for pallet photo analysis; custom AI agent required |
| Visual label presence and readability verification | TeamViewer Frontline AR (optional, SC5105) | — | — | **Yes** | TeamViewer AR covers guided picking, not automated AI photo verification; custom build required |
| Delivery blocking when mismatch detected | SAP S/4HANA Cloud Private Edition — Outbound Warehouse Management | `sap.s4:apiResource:WAREHOUSEOUTBDELIVERYORDER_0001:v1` (update) | — | Maybe | EWM API supports status updates; blocking logic must be implemented in agent |
| Multi-channel photo ingestion (fixed camera, handheld, mobile, web) | None | — | — | **Yes** | No standard SAP product supports multi-channel image ingestion; agent must handle this |

### Key findings

- SAP S/4HANA Cloud Private Edition (embedded EWM) provides all necessary OData APIs for delivery and HU data — no additional SAP product purchase required for the data layer.
- No MCP servers exist in the landscape for any of the relevant EWM/delivery APIs; direct OData integration via HTTP tool calls is the integration approach.
- The core gap is AI vision/computer vision for photo analysis — this is a custom capability requiring an LLM with vision capabilities (e.g., GPT-4o, Gemini Vision, or SAP AI Core multimodal model).
- Label verification requires two distinct AI tasks: (1) object detection to confirm physical label presence and readability, and (2) OCR/barcode extraction to read label content and compare against EWM data.
- Delivery blocking on mismatch is achievable via the Warehouse Outbound Delivery Order update API; the agent must control when this action is triggered.
- TeamViewer Frontline AR is mentioned in the SAP portfolio as an optional extension for outbound EWM but is a separate AR product, not a fit for automated AI photo verification.

## Recommendations

### EWM Pallet Verification Joule Agent

#### Executive Summary

Build a SAP Joule Agent using Joule Skills and Actions that enables warehouse workers to verify pallet HU labels against SAP EWM outbound delivery data through a conversational interface embedded in SAP S/4HANA or any SAP application that surfaces Joule.

#### Recommended Solution

A SAP Joule Agent composed of Joule Skills and Actions deployed via SAP AI Launchpad / SAP Build, with the following design:

**Joule Skills:**
- **`VerifyPalletLoading`** — the primary skill that orchestrates the end-to-end pallet verification flow; accepts a delivery number or HU barcode as input from the worker via natural language or structured input.
- **`LookUpHUByBarcode`** — sub-skill that resolves a scanned SSCC/barcode to its EWM delivery assignment when no delivery number is provided.
- **`GenerateVerificationReport`** — sub-skill that cross-references detected HUs against expected HUs and formats a structured pass/fail summary for the worker.

**Joule Actions (OData/REST API integrations):**
- **`GetOutboundDelivery`** — calls `OP_API_OUTBOUND_DELIVERY_SRV_0002` to retrieve delivery header, items, and assigned HU list from SAP S/4HANA EWM.
- **`GetHandlingUnitDetails`** — calls `OP_HANDLINGUNIT_0001` to fetch HU content, packing material, and delivery assignment details.
- **`BlockDelivery`** — calls the Warehouse Outbound Delivery Order update API to set a blocking reason when critical discrepancies are found (supervisor-controlled action).

The agent is surfaced to warehouse workers and supervisors via the Joule conversational UI embedded in SAP S/4HANA, SAP Mobile Start, or any SAP Fiori launchpad.

#### Problem Statement

Manual pallet loading checks are error-prone and slow. Warehouse workers rely on visual inspection and manual scanning to confirm HUs on a pallet match the outbound delivery, with no automated verification of label completeness. Errors (wrong HUs, missing labels) are often discovered only after shipment, resulting in costly returns, delivery disputes, and compliance failures.

#### Affected User Roles

- Warehouse operator / picker (performs loading verification via Joule chat)
- Warehouse supervisor (reviews flagged discrepancies and approves delivery blocking)
- Shipping coordinator (ensures delivery completion before goods issue)

#### Important factors

##### Native SAP Joule Integration
Leveraging Joule Skills and Actions ensures the agent is embedded directly in the SAP user experience — no external chat interface or separate application is required.

##### Real-time EWM data integration
Every verification is performed against live EWM data via Joule Actions calling standard OData APIs, ensuring accuracy even when deliveries are updated last-minute.

##### Low-code / declarative authoring
Joule Skills and Actions are defined declaratively, reducing the custom code footprint and enabling faster iteration and maintenance by SAP Build authors.

#### Potential risks

##### EWM API connectivity and latency
Real-time API calls to S/4HANA add latency. Mitigation: implement retry logic in Actions and surface clear error messages if the system is unreachable.

##### Delivery blocking misuse
Incorrect blocking of a valid delivery causes operational disruption. Mitigation: the BlockDelivery Action is gated behind a supervisor confirmation step in the skill flow.

##### Joule platform availability
Joule Skills and Actions require SAP AI Launchpad entitlement and appropriate BTP configuration. Mitigation: validate entitlement and landscape setup prior to implementation.

#### Recommended solution category

Joule Agent (Joule Skills & Actions)

#### Intent fit
90%
