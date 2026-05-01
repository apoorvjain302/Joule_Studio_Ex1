"""
EWM Pallet Verification Joule Agent — gateway service.

Serves the A2A agent card and exposes the Joule Skill and Action
definitions so that SAP AI Launchpad can discover and register them.
"""

import os
import glob
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="EWM Pallet Verification Agent", version="1.0.0")

BASE_DIR = Path(__file__).parent.parent

AGENT_CARD = {
    "name": "EWM Pallet Verification Agent",
    "version": "1.0.0",
    "description": (
        "Verifies outbound pallet HU labels against SAP EWM delivery data "
        "using AI photo analysis. Detects missing, extra, or unreadable HU "
        "labels, blocks deliveries on critical mismatches, and remediates "
        "incorrect picks by reversing warehouse tasks and creating replacement "
        "pick instructions."
    ),
    "capabilities": {
        "skills": [
            {
                "name": "VerifyPalletLoading",
                "description": (
                    "Primary skill. Accepts a pallet photo and delivery number "
                    "(or HU barcode), fetches live EWM data, runs AI vision "
                    "analysis, and produces a structured pass/fail HU verification report."
                ),
            },
            {
                "name": "LookUpHUByBarcode",
                "description": (
                    "Sub-skill. Resolves an SSCC barcode scan to its associated "
                    "EWM outbound delivery number and warehouse number."
                ),
            },
            {
                "name": "GenerateVerificationReport",
                "description": (
                    "Sub-skill. Cross-references detected HUs against expected "
                    "EWM delivery HUs and formats a pass/fail report card."
                ),
            },
            {
                "name": "RemediateIncorrectHU",
                "description": (
                    "Sub-skill. Cancels picking, reverses warehouse tasks for "
                    "incorrect HUs, and creates new warehouse tasks to pick "
                    "the correct HUs."
                ),
            },
            {
                "name": "SupervisorOverride",
                "description": (
                    "Sub-skill. Allows an authorised supervisor to release a "
                    "delivery block after reviewing the discrepancy report."
                ),
            },
        ]
    },
    "authentication": {"type": "bearer"},
    "supportedContentTypes": ["application/json", "image/jpeg", "image/png"],
    "url": os.environ.get("AGENT_URL", ""),
}


@app.get("/.well-known/agent.json")
def agent_card() -> JSONResponse:
    """A2A agent discovery endpoint."""
    return JSONResponse(content=AGENT_CARD)


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@app.get("/skills")
def list_skills() -> JSONResponse:
    """List all available Joule Skill definitions."""
    skills_dir = BASE_DIR / "skills"
    skills = []
    for path in sorted(skills_dir.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        skills.append(
            {
                "name": data.get("metadata", {}).get("name"),
                "version": data.get("metadata", {}).get("version"),
                "description": data.get("metadata", {}).get("description", "").strip(),
                "file": path.name,
            }
        )
    return JSONResponse(content={"skills": skills})


@app.get("/skills/{skill_name}")
def get_skill(skill_name: str) -> JSONResponse:
    """Return the full YAML definition for a named skill."""
    skills_dir = BASE_DIR / "skills"
    for path in skills_dir.glob("*.yaml"):
        with open(path) as f:
            data = yaml.safe_load(f)
        if data.get("metadata", {}).get("name") == skill_name:
            return JSONResponse(content=data)
    raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found.")


@app.get("/actions")
def list_actions() -> JSONResponse:
    """List all available Joule Action definitions."""
    actions_dir = BASE_DIR / "actions"
    actions = []
    for path in sorted(actions_dir.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        actions.append(
            {
                "name": data.get("metadata", {}).get("name"),
                "version": data.get("metadata", {}).get("version"),
                "description": data.get("metadata", {}).get("description", "").strip(),
                "file": path.name,
            }
        )
    return JSONResponse(content={"actions": actions})


@app.get("/actions/{action_name}")
def get_action(action_name: str) -> JSONResponse:
    """Return the full YAML definition for a named action."""
    actions_dir = BASE_DIR / "actions"
    for path in actions_dir.glob("*.yaml"):
        with open(path) as f:
            data = yaml.safe_load(f)
        if data.get("metadata", {}).get("name") == action_name:
            return JSONResponse(content=data)
    raise HTTPException(status_code=404, detail=f"Action '{action_name}' not found.")
