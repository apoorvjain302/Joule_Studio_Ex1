# Agent Guidelines

Technical constraints and patterns for building Pro-Code AI Agents. Follow these throughout specification execution.

## Tech Stack

- Python 3.13
- Agent framework defined in the `sap-agent-bootstrap` skill
- Agent2Agent (A2A) protocol
- Local execution only (in-memory storage, no deployment)

## Project Structure

- Asset root: `assets/<asset-name>/`
- Required structure: `asset.yaml`, `app/`
- Full layout from project root: `solution.yaml`, `assets/<asset-name>/asset.yaml`, `assets/<asset-name>/app/`
- `asset.yaml` must use `buildPath: .` and `/.well-known/agent.json` for all health probes
- Follow the `sap-agent-bootstrap` skill for project scaffolding — invoke directly from `assets/<asset-name>/`, use copy commands

## Key Constraints

- When working with LangChain or LangGraph, you MUST NEVER use the `create_react_agent` function (`from langgraph.prebuilt import create_react_agent`) as it has been deprecated in LangChain 1.0. Instead, you should use the `from langchain.agents import create_agent` function.
- **NEVER call SAP APIs directly** (no `requests`, `httpx`, or hand-rolled OData clients). All SAP API consumption MUST go through MCP servers via `gatewaySDK` + `MultiServerMCPClient`. Translation files are produced by the `mcp-translation-file` skill — the agent consumes them as tools, never as raw HTTP calls.
- Only use public APIs; mock any private systems (like S/4HANA) with minimal mock data
- Exception: AI Core is fully available at runtime via LiteLLM (environment variables provided)
- No Git operations, no authentication, no documentation/READMEs
- Update `requirements.txt` for any new dependencies
- Never modify `sys.path`
- Map SAP Joule Studio/Skills concepts to standard agent tools
- No `.env` files (environment variables supplied at runtime)


## Code Quality

- All Python code must compile with valid imports
- No `src.` import patterns
- All function parameters must be used in function body

## Agent Decorators

- The bootstrap template already includes decorator scaffolding — no separate skill invocation needed
- **NEVER add new decorated functions to `app/agent.py`** — the three from the bootstrap template (`@agent_model`, `@agent_config` for temperature, `@prompt_section`) are the complete and final set. `@agent_config` is not a general-purpose decorator; it exposes parameters to the SAP platform UI and is intentionally limited to temperature. All other values (thresholds, limits, counts, etc.) must be plain Python constants.
- Never mark decorator tasks complete until `sap_cloud_sdk.agent_decorators` imports exist in `app/agent.py`

## Agent Instrumentation
- ALL business logic steps MUST be instrumented with proper logging and OpenTelemetry spans
- Use milestones from the PRD's "Milestones" section (if available) or derive from the project input for business step instrumentation
- Each milestone must emit structured log statements on achievement and miss
- Log pattern: `[MILESTONE_ID].[achieved|missed]: [description]`
- Add OpenTelemetry custom spans for each business step (`@tracer.start_as_current_span`)
- Ensure `auto_instrument()` is called at top of `main.py` before any AI framework imports

## MCP Tool Integration

All SAP API integration MUST use this pattern. If the PRD or specification references any SAP API (OData, REST, events), MCP wiring is mandatory, not optional.

Tools are loaded via the Agent Gateway SDK — no URLs, no ORD IDs, no `MultiServerMCPClient`. The SDK discovers all registered MCP servers automatically and returns LangChain-compatible tools directly.

When writing system instructions for the agent, explicitly instruct the agent not to hallucinate data.

### Canonical Pattern

```python
from mcp_tools import get_mcp_tools

async def _load_tools() -> list:
    return await get_mcp_tools()
```

`mcp_tools.py` is the owned indirection layer produced by the bootstrap — import from there, never directly from `sap_cloud_sdk.agentgateway`. This is the target the test fixture patches.

Call `_load_tools()` lazily (not in `__init__`) — it makes network calls. Wire the result into the agent graph:

```python
class MyAgent:
    def __init__(self):
        self._tools = None

    async def _get_tools(self) -> list:
        if self._tools is None:
            self._tools = await _load_tools()
        return self._tools

    async def stream(self, query, context_id, ext_impl=None):
        tools = await self._get_tools()
        graph = self._build_graph(tools, system_prompt=get_system_prompt())
        ...
```

### Local Testing (IBD_TESTING)

**Do NOT branch on `IBD_TESTING` in application code.** The `conftest.py` monkey-patches `mcp_tools.get_mcp_tools` before any agent code runs. Agent code stays identical in production and tests.

The patch returns `StructuredTool` instances built from `mcp-mock.json`. Generate `mcp-mock.json` with the `mcp-mock-config` skill before running tests.

## Testing

Working directory for all test operations: `assets/<asset-name>/` (asset root).

### Setup

1. Install test dependencies: `pip install -r requirements-test.txt`

### Boilerplate Files

- `conftest.py` — shared fixtures, custom markers, writes `test_report.json` on full runs
- `pytest.ini` — configures test discovery (`prebuilt_tests/`, `tests/`), default flags, markers
- `requirements-test.txt` — test dependencies
- `prebuilt_tests/` — pre-built structure and server tests; NEVER modify these

### Writing Tests

- All generated tests go in `assets/<asset-name>/tests/` (NOT inside `app/`)
- Unit tests: exactly one per tool; run each immediately after writing
- Integration test: one end-to-end test with real LLM (AI Core env vars always available)
- Mock external non-AI systems (e.g. S/4HANA), never mock the LLM

### Running Tests

- ALWAYS invoke as just `pytest` from asset root — no paths, no `--cov`, no `--json-report`, no extra flags
- `pytest.ini` configures everything; extra CLI flags conflict with ini settings
- Only exception: targeting a single test: `pytest path/to/test_file.py::test_name`
- Coverage must be ≥ 70%; if below, add targeted tests until threshold met
- Final `pytest` run (no args) MUST produce `test_report.json` — this only happens on full runs without arguments

## Validation Checklist

Run these verifications before marking implementation complete:

```bash
# Instrumentation
grep -r "M[0-9]\.achieved" assets/<asset-name>/app/     # must return results

# Decorators
grep -r "sap_cloud_sdk.agent_decorators" assets/<asset-name>/app/  # must return results
grep -c "^@agent_model\|^@agent_config\|^@prompt_section" assets/<asset-name>/app/agent.py  # must return 3 (one @agent_model, one @agent_config for temperature, one @prompt_section)

# Test report
ls assets/<asset-name>/test_report.json                  # must exist
```

## MCP Translation Files, MCP Servers & Mock Tools (Post-Implementation)

After all asset spec TODO items are complete, run the applicable path(s):

### Path A — API spec files (OData/REST, no existing MCP server)

Run when `specification/<asset-name>/api-specs/` contains API spec files (e.g. `supplier-invoices.json`) but **no** `mcp-spec-*.json` files.

1. **MCP Translation Files:** Invoke the `mcp-translation-file` skill. It generates translation files to `specification/<asset-name>/mcps/`. Do NOT manually create translation files.
2. **MCP Server Assets:** For each translation file in `specification/<asset-name>/mcps/`:
   - Create asset folder: `assets/<mcp-server-name>/` with `asset.yaml` and copy translation file
   - Name pattern: `{domain}-{purpose}-mcp-server` (e.g. `s4-dispute-mcp-server`)
   - Register in `solution.yaml` under `assets`
   - Add to agent's `asset.yaml` under `tools.mcp-servers` with ORD IDs

### Path B — MCP spec files (existing MCP server with known ORD ID)

Run when `specification/<asset-name>/api-specs/` contains `mcp-spec-*.json` files captured during API discovery (step 2a).

No translation or MCP server asset creation needed — the MCP server already exists externally.

### MCP Server Dependencies in asset.yaml

For **every** MCP server the agent uses (Path A or Path B), add a corresponding entry to the agent's `asset.yaml` under `requires`:

```yaml
requires:
  - name: <mcp-server-name>
    kind: mcp-server
    ordId: <ord-id>
```

This applies to both internally created MCP server assets (Path A) and externally existing MCP servers (Path B). The `ordId` is the same ORD ID referenced under `tools.mcp-servers`.

## Agent Evaluation (Post-Implementation)

Run after all tests pass and the agent is working locally.

### Step 1: Generate tool schema

Invoke the `sap-aeval-generate-tool-schema` skill from the asset root (`assets/<asset-name>/`). It scans the `app/` directory, extracts all tool function signatures and docstrings, and writes `tools.json` to the current working directory.

### Step 2: Generate eval test cases

Invoke the `sap-aeval-generate-testcase` skill from the same asset root, passing:
- The PRD file path (e.g. `specification/<asset-name>/specification.md`)
- `tools.json` generated in Step 1

The skill writes eval criteria to `aeval/eval.yaml` and YAML test cases to `aeval/testcases/`. Review the generated test cases and replace any placeholder values (e.g. `<param_name:example>`) with realistic data before running evaluations.


