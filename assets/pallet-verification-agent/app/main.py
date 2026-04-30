# CRITICAL: Initialize telemetry BEFORE importing AI frameworks
from sap_cloud_sdk.aicore import set_aicore_config
from sap_cloud_sdk.core.telemetry import auto_instrument

set_aicore_config()
auto_instrument()

import logging
import os

import click
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from starlette.applications import Starlette
from starlette.routing import Mount
from ord import create_ord_routes

from agent_executor import AgentExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))


@click.command()
@click.option("--host", default=HOST)
@click.option("--port", default=PORT)
def main(host: str, port: int):
    skill = AgentSkill(
        id="pallet-verification-agent",
        name="EWM Pallet Verification Agent",
        description="AI-powered pallet verification agent for SAP EWM outbound loading — detects HU labels via vision AI and cross-references against live EWM delivery data.",
        tags=["pallet", "verification", "ewm", "warehouse"],
        examples=[
            "Verify pallet for delivery 0080001234",
            "Check if pallet HUs match outbound delivery",
        ],
    )
    agent_card = AgentCard(
        name="EWM Pallet Verification Agent",
        description="AI-powered pallet verification agent for SAP EWM outbound loading — detects HU labels via vision AI and cross-references against live EWM delivery data.",
        url=os.environ.get("AGENT_PUBLIC_URL", f"http://{host}:{port}/"),
        version="1.0.0",
        default_input_modes=["text", "text/plain"],
        default_output_modes=["text", "text/plain"],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        skills=[skill],
    )
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=DefaultRequestHandler(
            agent_executor=AgentExecutor(),
            task_store=InMemoryTaskStore(),
        ),
    )
    # Build A2A app
    a2a_app = server.build()

    # Combine ORD routes with A2A app
    # ORD routes are matched first, then all other requests go to the A2A app
    combined_app = Starlette(
        routes=[
            *create_ord_routes(),
            Mount("/", app=a2a_app),
        ]
    )

    logger.info(f"Starting agent with ORD endpoint at http://{host}:{port}/.well-known/open-resource-discovery")
    uvicorn.run(combined_app, host=host, port=port)


if __name__ == "__main__":
    main()
