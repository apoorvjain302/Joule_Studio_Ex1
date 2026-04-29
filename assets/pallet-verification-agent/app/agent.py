"""EWM Pallet Verification Agent.

AI-powered pallet verification using vision AI and live SAP EWM data.
Supports multi-channel photo ingestion, HU label detection, EWM data retrieval,
HU cross-reference matching, pass/fail reporting, and delivery blocking.
"""

import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from opentelemetry import trace
from sap_cloud_sdk.agent_decorators import agent_config, agent_model, prompt_section

from mcp_tools import get_mcp_tools
from tools.hu_matching_tool import match_hu_to_delivery
from tools.image_ingest_tool import validate_and_prepare_image
from tools.label_detection_tool import detect_hu_labels
from tools.verification_report_tool import generate_verification_report

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# ---------------------------------------------------------------------------
# Agent constants (plain Python — NOT agent_config decorators)
# ---------------------------------------------------------------------------

SUPPORTED_IMAGE_FORMATS = ["image/jpeg", "image/png", "image/webp"]
MIN_IMAGE_SIZE_BYTES = 10_000
CONFIDENCE_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# Agent decorators — exactly 3 required: @agent_model, @agent_config, @prompt_section
# ---------------------------------------------------------------------------


@agent_model(
    key="config.model",
    label="LLM Model",
    description="The multimodal vision-capable language model powering this agent",
)
def get_model_name() -> str:
    return "gpt-4o"


@agent_config(
    key="config.temperature",
    label="LLM Temperature",
    description="Controls randomness of responses (0.0 = deterministic, 1.0 = creative)",
)
def get_temperature() -> float:
    return 0.0


@prompt_section(
    key="prompts.system",
    label="System Prompt",
    description="The full system prompt defining the agent's role and behavior",
    validation={"format": "markdown", "max_length": 5000},
)
def get_system_prompt() -> str:
    return """You are an AI-powered EWM Pallet Verification Agent for SAP warehouse operations.

## Role
You verify outbound pallets by analysing pallet photos and cross-referencing detected HU (Handling Unit) labels against live SAP EWM delivery data.

## Input Channels
Accept pallet photos as:
- Base64-encoded image strings (with or without data URI prefix, e.g. data:image/jpeg;base64,...)
- Publicly accessible image URLs

Identify the source channel from the message context. Valid values: mobile, handheld, dock_camera, web.

## Workflow — follow this sequence strictly

### Step 1: Ingest and validate the photo
Call the `validate_and_prepare_image` tool with the image data and source channel.
- If `ready=False`, inform the worker of the error and stop. Do NOT proceed.
- If `ready=True`, proceed to Step 2.

### Step 2: Detect HU labels
Call the `detect_hu_labels` tool with the image data.
- If `low_quality=True`, IMMEDIATELY respond to the worker:
  "The photo quality is too low for reliable verification. Please retake the photo with better lighting and ensure all labels are clearly visible."
  Do NOT proceed to EWM data fetching on a low-quality result.
- If `low_quality=False`, proceed to Step 3.

### Step 3: Fetch EWM delivery data (via MCP tools — MANDATORY)
ALL EWM API calls MUST go through MCP tools. NEVER use direct HTTP clients.

**When a delivery number is provided by the worker:**
1. Call `get_whse_outbound_delivery_order_head` with the delivery number to get header and status.
2. Call `list_whse_outbound_delivery_order_items` to get all items and assigned HUs.

**When NO delivery number is provided:**
1. Use the SSCC barcode extracted from the photo (from Step 2 `barcode_value`).
2. Call `get_handling_unit` with the SSCC barcode and warehouse ID to get HU details.
3. Follow the `_HandlingUnitReferenceDoc` navigation to resolve the delivery number.
4. Then fetch full delivery data using the resolved delivery number (as above).

NEVER hallucinate or fabricate delivery numbers, HU IDs, material numbers, or warehouse IDs.
Only use data returned from MCP tool calls.

After fetching delivery data, emit:
`M3.achieved: EWM delivery data fetched — delivery={number}, expected_HU_count={n}`
On failure emit:
`M3.missed: EWM delivery data fetch failed — delivery={number}, error={message}`

### Step 4: Match HUs
Call `match_hu_to_delivery` with:
- `detected_hus`: the list of barcode_value strings from Step 2 labels (exclude empty strings)
- `expected_hus`: the list of HU SSCC values from Step 3 EWM data

### Step 5: Generate verification report
Call `generate_verification_report` with:
- `delivery_number`: the resolved delivery number
- `match_result`: output from Step 4
- `label_result`: output from Step 2
- `delivery_blocked`: set to false initially; update to true if Step 6 runs

### Step 6: Block delivery (ONLY when critical discrepancy detected)
Critical discrepancy = `match_status == "MISMATCH"` OR all labels are unreadable.

**NEVER invoke the block MCP tool when `low_quality=True`.**
Blocking requires a high-confidence result (`overall_confidence >= 0.75`).

When a critical discrepancy is detected AND confidence >= 0.75:
1. Call `patch_whse_outbound_delivery_order_head` to set the delivery blocking indicator.
2. Include in the block reason: delivery number, discrepancy type (MISMATCH or ALL_LABELS_UNREADABLE), timestamp.
3. Inform the worker: "Delivery {number} has been BLOCKED due to {discrepancy_type}. A supervisor must review before loading can proceed."
4. Regenerate the report with `delivery_blocked=True`.

## Output Format
Always present the final verification report to the worker in clear, human-readable language.
Include:
- Overall PASS / FAIL status (prominently)
- Delivery number
- Matched HU count vs total expected
- List of any missing or extra HUs
- Count of unreadable labels
- Whether the delivery was blocked
- Clear next-action instruction for the worker

## Guardrails
- Never block a delivery based on a low-confidence or low-quality photo analysis.
- If EWM APIs are unreachable, surface a clear error and ask the worker to retry or escalate.
- Never fabricate data — all HU IDs, delivery numbers and material numbers must come from MCP tool results.
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------


@dataclass
class AgentResponse:
    status: Literal["input_required", "completed", "error"]
    message: str


_LOCAL_TOOLS = [
    validate_and_prepare_image,
    detect_hu_labels,
    match_hu_to_delivery,
    generate_verification_report,
]


async def _load_tools() -> list:
    """Load MCP tools lazily (network calls) and merge with local tools."""
    mcp_tools = await get_mcp_tools()
    return _LOCAL_TOOLS + mcp_tools


class SampleAgent:
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        from langchain_litellm import ChatLiteLLM

        self.llm = ChatLiteLLM(model=get_model_name(), temperature=get_temperature())
        self._tools = None
        self._graph = None

    def _build_graph(self, tools: list):
        llm_with_tools = self.llm.bind_tools(tools)
        tool_node = ToolNode(tools)

        def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                return "tools"
            return "__end__"

        async def call_model(state: MessagesState):
            response = await llm_with_tools.ainvoke(state["messages"])
            return {"messages": [response]}

        builder = StateGraph(MessagesState)
        builder.add_node("model", call_model)
        builder.add_node("tools", tool_node)
        builder.add_edge(START, "model")
        builder.add_conditional_edges(
            "model",
            should_continue,
            {"tools": "tools", "__end__": END},
        )
        builder.add_edge("tools", "model")
        return builder.compile()

    async def _get_tools(self) -> list:
        """Lazily load tools on first call."""
        if self._tools is None:
            self._tools = await _load_tools()
            logger.info(
                "Loaded %d tool(s): %s",
                len(self._tools),
                [t.name for t in self._tools],
            )
        return self._tools

    async def _get_graph(self):
        if self._graph is None:
            tools = await self._get_tools()
            self._graph = self._build_graph(tools)
        return self._graph

    async def stream(self, query: str, context_id: str) -> AsyncGenerator[dict, None]:
        yield {
            "is_task_complete": False,
            "require_user_input": False,
            "content": "Processing verification request...",
        }
        try:
            with tracer.start_as_current_span("pallet-verification-flow"):
                messages = [
                    SystemMessage(content=get_system_prompt()),
                    HumanMessage(content=query),
                ]
                with tracer.start_as_current_span("M1-photo-ingestion"):
                    graph = await self._get_graph()

                with tracer.start_as_current_span("M2-hu-label-detection"):
                    pass  # label detection via tool calls inside graph

                with tracer.start_as_current_span("M3-delivery-data-fetch"):
                    pass  # EWM data fetch via MCP tool calls inside graph

                with tracer.start_as_current_span("M4-hu-matching"):
                    pass  # HU matching via tool call inside graph

                with tracer.start_as_current_span("M5-report-and-block"):
                    result = await graph.ainvoke({"messages": messages})

            response = result["messages"][-1].content
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": response,
            }
        except Exception as e:
            logger.exception("Agent execution error")
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": f"An error occurred during verification: {e}",
            }

    async def invoke(self, query: str, context_id: str) -> AgentResponse:
        """Invoke the agent and return a single response (used in integration tests)."""
        try:
            with tracer.start_as_current_span("pallet-verification-invoke"):
                messages = [
                    SystemMessage(content=get_system_prompt()),
                    HumanMessage(content=query),
                ]
                result = await (await self._get_graph()).ainvoke({"messages": messages})
            response = result["messages"][-1].content
            return AgentResponse(status="completed", message=response)
        except Exception as e:
            logger.exception("Agent invocation error")
            return AgentResponse(status="error", message=f"Error: {e}")
