# Specification

> **Guidelines**: Read [guidelines.md](./guidelines.md) before executing ANY tasks below.

Check off items as completed.

## Solution Setup

- [ ] Create asset directories:
  ```
  mkdir -p assets/pallet-verification-agent/
  mkdir -p assets/ewm-outbound-delivery-mcp-server/
  mkdir -p assets/ewm-handling-unit-mcp-server/
  ```
- [ ] Invoke `setup-solution` skill to create `solution.yaml` and `asset.yaml` files for all three assets:
  - `pallet-verification-agent` (type: agent)
  - `ewm-outbound-delivery-mcp-server` (type: mcp-server)
  - `ewm-handling-unit-mcp-server` (type: mcp-server)
- [ ] Validate all `asset.yaml` and `solution.yaml` files exist and are well-formed

## Asset Implementation

- [ ] Execute `specification/pallet-verification-agent/specification.md` (all items)

## MCP Server Assets (Path A — OData spec → MCP translation files)

Run after all `pallet-verification-agent` code items are complete:

- [ ] Invoke `mcp-translation-file` skill against:
  - `specification/pallet-verification-agent/api-specs/warehouse-outbound-delivery-order.json`
  - `specification/pallet-verification-agent/api-specs/outbound-delivery.json`
  - Output: `specification/pallet-verification-agent/mcps/ewm-outbound-delivery-translation.json`
- [ ] Invoke `mcp-translation-file` skill against:
  - `specification/pallet-verification-agent/api-specs/handling-unit.json`
  - Output: `specification/pallet-verification-agent/mcps/ewm-handling-unit-translation.json`
- [ ] Populate `assets/ewm-outbound-delivery-mcp-server/` with `asset.yaml` and copy `ewm-outbound-delivery-translation.json` into it; register in `solution.yaml`
- [ ] Populate `assets/ewm-handling-unit-mcp-server/` with `asset.yaml` and copy `ewm-handling-unit-translation.json` into it; register in `solution.yaml`
- [ ] Add both MCP servers to `assets/pallet-verification-agent/asset.yaml` under `tools.mcp-servers` and `requires`:
  ```yaml
  requires:
    - name: ewm-outbound-delivery-mcp-server
      kind: mcp-server
      ordId: sap.s4:apiResource:WAREHOUSEOUTBDELIVERYORDER_0001:v1
    - name: ewm-handling-unit-mcp-server
      kind: mcp-server
      ordId: sap.s4:apiResource:OP_HANDLINGUNIT_0001:v1
  ```
- [ ] Generate `mcp-mock.json` using `mcp-mock-config` skill from `assets/pallet-verification-agent/`
- [ ] Re-run `pytest` from `assets/pallet-verification-agent/` (no args) to confirm all tests pass with mock data and `test_report.json` is generated
