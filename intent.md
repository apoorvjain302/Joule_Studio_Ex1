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

### EWM Pallet Verification AI Agent

#### Executive Summary

Build a pro-code Python AI agent that accepts pallet photos from multiple input channels, uses a multimodal LLM to detect and read HU labels, fetches the expected HU list from SAP EWM via OData APIs, and produces a structured verification report — alerting the worker and optionally blocking the delivery if discrepancies are found.

#### Recommended Solution

A Python-based AI agent (A2A protocol) deployed on SAP App Foundation with the following tools:
- **`analyze_pallet_photo`** — sends image to a multimodal LLM (vision model) to detect all visible HU labels, assess physical presence/readability, and extract barcode/text data.
- **`get_outbound_delivery`** — calls SAP EWM OData API (`OP_API_OUTBOUND_DELIVERY_SRV_0002`) to fetch delivery header, items, and assigned HU list by delivery number.
- **`get_handling_unit_details`** — calls `OP_HANDLINGUNIT_0001` to retrieve HU content, packing material, and delivery assignment.
- **`lookup_hu_by_barcode`** — resolves a scanned HU barcode/SSCC number to its EWM delivery assignment when no delivery number is explicitly provided.
- **`generate_verification_report`** — cross-references detected HUs vs. expected HUs, flags missing/extra HUs and label issues, returns a structured pass/fail report.
- **`block_delivery`** — calls the Warehouse Outbound Delivery Order update API to set a blocking reason when critical discrepancies are found.

The agent is invoked by warehouse workers across supported channels: mobile chat UI, web upload form, handheld scanner, or triggered automatically by a fixed dock camera.

#### Problem Statement

Manual pallet loading checks are error-prone and slow. Warehouse workers rely on visual inspection and manual scanning to confirm HUs on a pallet match the outbound delivery, with no automated verification of label completeness. Errors (wrong HUs, missing labels) are often discovered only after shipment, resulting in costly returns, delivery disputes, and compliance failures.

#### Affected User Roles

- Warehouse operator / picker (performs loading and photo capture)
- Warehouse supervisor (reviews flagged discrepancies and release decisions)
- Shipping coordinator (ensures delivery completion before goods issue)

#### Important factors

##### Eliminates manual verification errors
AI vision replaces error-prone manual checks, detecting missing or damaged labels and HU mismatches that a rushed worker might overlook.

##### Real-time EWM data integration
Every verification is performed against live EWM data — no static lists or cached data — ensuring accuracy even when deliveries are updated last-minute.

##### Multi-modal input flexibility
Supporting fixed cameras, handhelds, mobile devices, and web upload ensures the agent fits into any warehouse floor setup without hardware changes.

#### Potential risks

##### Multimodal LLM accuracy on low-quality images
Poor lighting, motion blur, or partial occlusion of labels can reduce OCR and label detection accuracy. Mitigation: implement confidence scoring and prompt the worker to retake the photo if confidence is below threshold.

##### EWM API connectivity and latency
Real-time API calls to S/4HANA add latency to the verification flow. Mitigation: implement retry logic and surface clear error messages if the system is unreachable.

##### Delivery blocking misuse
Incorrect blocking of a valid delivery causes operational disruption. Mitigation: implement a supervisor override tool and log all blocking actions.

#### Recommended solution category

AI Agent

#### Intent fit
88%
