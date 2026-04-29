# Specification: pallet-verification-agent

> **Guidelines**: Read [guidelines.md](../guidelines.md) and [guidelines-agent.md](../guidelines-agent.md) before executing ANY tasks below. Follow all constraints described there throughout execution.

## Basic Setup

- [ ] Read the project input (`product-requirements-document.md` and `intent.md`)
- [ ] Bootstrap agent code in `assets/pallet-verification-agent/` using skill `sap-agent-bootstrap` (invoke from inside `assets/pallet-verification-agent/`, use copy commands — do NOT create files manually)
- [ ] Install dependencies, validate the agent starts and responds at `/.well-known/agent.json`

## REQ-01 — Multi-Channel Photo Ingestion

The agent accepts pallet images from any supported input channel (mobile device, handheld scanner, fixed dock camera, web upload). Images arrive as base64-encoded strings or publicly accessible URLs in the conversation context.

- [ ] Add Python constant `SUPPORTED_IMAGE_FORMATS = ["image/jpeg", "image/png", "image/webp"]` in `app/agent.py`
- [ ] Add Python constant `MIN_IMAGE_SIZE_BYTES = 10_000` (10 KB minimum) in `app/agent.py`
- [ ] In the agent system prompt (`@prompt_section`), instruct the agent to accept a pallet photo as a base64-encoded image or a publicly accessible image URL, and to identify the source channel from the message context (valid values: `mobile`, `handheld`, `dock_camera`, `web`)
- [ ] Implement `app/tools/image_ingest_tool.py` with a `validate_and_prepare_image(image_data: str, source_channel: str) -> dict` tool function that:
  - Accepts `image_data` (base64 string or URL) and `source_channel` (string)
  - Validates the image format and minimum size
  - Returns `{"image_id": str, "channel": str, "ready": bool, "error": str | None}`
  - On success emits log: `M1.achieved: pallet photo ingested successfully from channel={channel}, image_id={id}`
  - On failure emits log: `M1.missed: pallet photo ingestion failed — invalid format or resolution below threshold`

## REQ-02 & REQ-08 — AI Vision-Based HU Label Detection with Confidence Scoring

The agent uses the multimodal LLM (vision model) to detect HU labels on the pallet photo, assess their physical presence and readability, and extract barcode/SSCC values.

- [ ] Set the agent model to a multimodal/vision-capable model in `@agent_model` decorator (e.g. `gpt-4o`)
- [ ] Add Python constant `CONFIDENCE_THRESHOLD = 0.75` in `app/agent.py`
- [ ] Implement `app/tools/label_detection_tool.py` with a `detect_hu_labels(image_data: str) -> dict` tool function that:
  - Calls the LLM via LiteLLM with the image and a structured prompt asking the model to:
    - Count all visible HU labels on the pallet
    - For each label: assess `present` (bool), `readable` (bool), `confidence` (float 0–1), and extract `barcode_value` (string, empty if unreadable)
  - Returns `{"labels": list[dict], "overall_confidence": float, "low_quality": bool}`
  - Sets `low_quality = True` when `overall_confidence < CONFIDENCE_THRESHOLD`
  - On success emits log: `M2.achieved: HU labels detected — count={n}, confidence={score}, low_readability_flags={k}`
  - On failure/low-confidence emits log: `M2.missed: HU label detection failed or confidence below threshold — retake requested`
- [ ] In the system prompt, instruct the agent: if the `detect_hu_labels` tool returns `low_quality=True`, immediately respond to the worker asking them to retake the photo with better lighting or angle — do NOT proceed to EWM data fetching on low-quality results

## REQ-03, REQ-04, REQ-05 — Live EWM Data Retrieval and Delivery Resolution

The agent retrieves outbound delivery and HU data in real time from SAP EWM via MCP tools. **All EWM API calls MUST go through MCP tools — never use direct HTTP clients.**

**API specs for MCP translation (stored in `specification/pallet-verification-agent/api-specs/`):**

| File | ORD ID | Key endpoints used |
|------|--------|--------------------|
| `warehouse-outbound-delivery-order.json` | `sap.s4:apiResource:WAREHOUSEOUTBDELIVERYORDER_0001:v1` | `GET /WhseOutboundDeliveryOrderHead/{EWMOutboundDeliveryOrder}` (header + status), `GET /WhseOutboundDeliveryOrderHead/{EWMOutboundDeliveryOrder}/_WhseOutbDeliveryOrderItem` (all items), `PATCH /WhseOutboundDeliveryOrderHead/{EWMOutboundDeliveryOrder}` (update/block) |
| `handling-unit.json` | `sap.s4:apiResource:OP_HANDLINGUNIT_0001:v1` | `GET /HandlingUnit/{HandlingUnitExternalID}/{Warehouse}` (HU header), `GET /HandlingUnit/{HandlingUnitExternalID}/{Warehouse}/_HandlingUnitReferenceDoc` (delivery link), `GET /HandlingUnitItem` (packed items) |
| `outbound-delivery.json` | `sap.s4:apiResource:OP_API_OUTBOUND_DELIVERY_SRV_0002:v2` | `GET /A_OutbDeliveryHeader('{DeliveryDocument}')` (delivery header), `GET /A_OutbDeliveryHeader('{DeliveryDocument}')/to_HandlingUnitHeaderDelivery` (HUs on delivery), `GET /A_OutbDeliveryItem` (line items) |

**MCP tool wiring:**
- [ ] Wire MCP tool loading in `app/agent.py` using canonical pattern from guidelines:
  ```python
  from mcp_tools import get_mcp_tools
  async def _load_tools() -> list:
      return await get_mcp_tools()
  ```
- [ ] Wire `_load_tools()` lazily into the agent graph (call in `_get_tools()`, not in `__init__`)
- [ ] Generate `mcp-mock.json` using the `mcp-mock-config` skill **before running tests** (required for unit and integration tests)

**In the system prompt (`@prompt_section`), instruct the agent to:**
- [ ] When a delivery number is provided: call the `get_whse_outbound_delivery_order_head` MCP tool and then `list_whse_outbound_delivery_order_items` to get the full HU list
- [ ] When no delivery number is provided: call `get_handling_unit` with the SSCC barcode extracted from the photo plus the warehouse ID, then follow `_HandlingUnitReferenceDoc` to resolve the delivery number; then fetch full delivery data
- [ ] Never hallucinate or fabricate delivery numbers, HU IDs, or material numbers — only use data returned from MCP tool calls
- [ ] After fetching delivery data: emit log `M3.achieved: EWM delivery data fetched — delivery={number}, expected_HU_count={n}`; on failure emit `M3.missed: EWM delivery data fetch failed — delivery={number}, error={message}`

## REQ-03 & REQ-04 (continued) — HU Cross-Reference Matching

- [ ] Implement `app/tools/hu_matching_tool.py` with a `match_hu_to_delivery(detected_hus: list, expected_hus: list) -> dict` tool function:
  - `detected_hus`: list of SSCC/barcode strings extracted from the pallet photo by `detect_hu_labels`
  - `expected_hus`: list of SSCC strings from the EWM delivery HU assignment
  - Returns:
    ```json
    {
      "matched": ["HU001", "HU002"],
      "missing_from_pallet": ["HU003"],
      "extra_on_pallet": ["HU004"],
      "unreadable_labels": 0,
      "match_status": "FULL_MATCH"
    }
    ```
  - `match_status = "FULL_MATCH"` when all expected HUs detected AND no extras
  - `match_status = "PARTIAL_MATCH"` when some HUs match but gaps exist
  - `match_status = "MISMATCH"` when no expected HUs are detected at all
  - On success emits log: `M4.achieved: HU matching completed — matched={n}, missing={m}, extra={e}, unreadable={u}`
  - On failure (empty inputs) emits log: `M4.missed: HU matching could not be completed — insufficient label data or delivery data unavailable`

## REQ-06 — Structured Pass/Fail Verification Report

- [ ] Implement `app/tools/verification_report_tool.py` with a `generate_verification_report(delivery_number: str, match_result: dict, label_result: dict, delivery_blocked: bool) -> dict` tool function:
  - Returns:
    ```json
    {
      "overall_status": "PASS",
      "delivery_number": "0080001234",
      "matched_hu_count": 4,
      "total_expected_hu_count": 4,
      "missing_hus": [],
      "extra_hus": [],
      "unreadable_labels": 0,
      "delivery_blocked": false,
      "summary": "All 4 HUs verified. Pallet matches outbound delivery 0080001234. Ready to load."
    }
    ```
  - `overall_status = "PASS"` only when `match_status == "FULL_MATCH"` AND all labels are readable
  - `overall_status = "FAIL"` for any mismatch, missing HU, extra HU, or unreadable label
  - On success emits log: `M5.achieved: verification report delivered — status={PASS|FAIL}, delivery_blocked={true|false}`
  - On failure emits log: `M5.missed: verification report generation failed — worker notified to escalate`

## REQ-07 — Delivery Blocking on Critical Discrepancy

Critical discrepancy = `match_status == "MISMATCH"` (zero expected HUs detected) OR all labels unreadable.

- [ ] In the system prompt, instruct the agent to:
  - Call the `patch_whse_outbound_delivery_order_head` MCP tool to set a blocking indicator on the EWM delivery when a critical discrepancy is detected
  - **NEVER invoke the block MCP tool when `low_quality=True`** — blocking requires a high-confidence analysis result (`overall_confidence >= CONFIDENCE_THRESHOLD`)
  - Include in the block call reason: delivery number, discrepancy type (MISMATCH or ALL_LABELS_UNREADABLE), timestamp
  - Inform the worker that the delivery has been blocked and a supervisor must review

## Business Step Instrumentation

- [ ] Import OpenTelemetry tracer at top of `app/agent.py` (after `auto_instrument()` in `main.py`):
  ```python
  import logging
  from opentelemetry import trace
  logger = logging.getLogger(__name__)
  tracer = trace.get_tracer(__name__)
  ```
- [ ] Wrap each business step with a named OpenTelemetry span in agent flow methods:
  - `M1-photo-ingestion` span — wraps the call to `validate_and_prepare_image` tool
  - `M2-hu-label-detection` span — wraps the call to `detect_hu_labels` tool
  - `M3-delivery-data-fetch` span — wraps EWM MCP tool calls for delivery and HU data
  - `M4-hu-matching` span — wraps the call to `match_hu_to_delivery` tool
  - `M5-report-and-block` span — wraps `generate_verification_report` and conditional block MCP call
- [ ] Emit structured log statements in each tool function following the exact patterns from the PRD Milestones section (M1–M5 achieved/missed)
- [ ] Verify `auto_instrument()` is called at top of `main.py` before any AI framework imports

## Testing

- [ ] `conftest.py` only sets `IBD_TESTING=true` — this causes the agent to run with mock MCP tool results during tests
- [ ] Write `tests/test_image_ingest_tool.py` — test: valid JPEG base64 input → `ready=True`; invalid format → `ready=False` with error; size below minimum → `ready=False`; run immediately after writing
- [ ] Write `tests/test_label_detection_tool.py` — mock LLM response for: (1) 3 readable labels, high confidence → `low_quality=False`; (2) 3 labels low confidence → `low_quality=True`; (3) all labels unreadable → `low_quality=True`; run immediately after writing
- [ ] Write `tests/test_hu_matching_tool.py` — test: exact match → `FULL_MATCH`; one missing HU → `PARTIAL_MATCH`; all wrong HUs → `MISMATCH`; empty `detected_hus` list → `M4.missed` log; run immediately after writing
- [ ] Write `tests/test_verification_report_tool.py` — test: FULL_MATCH with all readable labels → `PASS`; PARTIAL_MATCH → `FAIL`; all unreadable labels → `FAIL`; `delivery_blocked=True` in report; run immediately after writing
- [ ] Write `tests/test_agent_integration.py` — end-to-end test: call `agent.invoke()` with a sample base64 test image (small 1x1 pixel JPEG encoded) and a delivery number `0080001234`; mock EWM MCP tools via `conftest.py` patch returning sample delivery data with 3 HUs; assert response contains `overall_status`; use real LLM (AI Core env vars always available); run immediately after writing
- [ ] Run `pytest` from `assets/pallet-verification-agent/` (no args) — if coverage < 70%, add tests until threshold met
- [ ] Verify `assets/pallet-verification-agent/app/agent.py` has exactly 3 decorated functions — run `grep -c "^@agent_model\|^@agent_config\|^@prompt_section" assets/pallet-verification-agent/app/agent.py` and confirm output is `3`
- [ ] Run `pytest` again from `assets/pallet-verification-agent/` (no args) to generate final `test_report.json`
- [ ] Verify `test_report.json` exists in `assets/pallet-verification-agent/`

## Agent Evaluation

- [ ] Invoke `sap-aeval-generate-tool-schema` skill from `assets/pallet-verification-agent/` to generate `tools.json`
- [ ] Invoke `sap-aeval-generate-testcase` skill from `assets/pallet-verification-agent/`, passing `../../specification/pallet-verification-agent/specification.md` and `tools.json`
- [ ] Review `aeval/testcases/` YAML files; replace all placeholder values with realistic EWM data (e.g. delivery `0080001234`, HU SSCCs like `00340123450000012345`, warehouse `WH01`)
