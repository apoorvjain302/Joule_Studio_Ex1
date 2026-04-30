import json
import logging
import os
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)

# Paths to the ORD documents (stored as static JSON files in app/ord/)
ORD_BASE_PATH = Path(__file__).parent / "ord"
ORD_SYSTEM_VERSION_PATH = ORD_BASE_PATH / "document-system-version.json"
ORD_SYSTEM_INSTANCE_PATH = ORD_BASE_PATH / "document-system-instance.json"


def load_ord_document(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load ORD document from {path}: {e}")
        raise


def inject_base_url(document: dict, base_url: str) -> dict:
    doc_str = json.dumps(document)
    doc_str = doc_str.replace("{{AGENT_BASE_URL}}", base_url)
    return json.loads(doc_str)


async def well_known_ord_config(request: Request) -> JSONResponse:
    config = {
        "openResourceDiscoveryV1": {
            "documents": [
                {
                    "url": "/open-resource-discovery/v1/documents/system-version",
                    "accessStrategies": [{"type": "open"}],
                    "perspective": "system-version"
                },
                {
                    "url": "/open-resource-discovery/v1/documents/system-instance",
                    "accessStrategies": [
                        {
                            "type": "custom",
                            "customType": "sap.xref:open-global-tenant-id:v1",
                            "customDescription": "The metadata information is openly accessible but system instance aware. The tenant is selected by providing a SAP global tenant ID header."
                        },
                        {
                            "type": "custom",
                            "customType": "sap.xref:open-local-tenant-id:v1",
                            "customDescription": "The metadata information is openly accessible but system instance aware. The tenant is selected by providing a local tenant ID header."
                        }
                    ],
                    "perspective": "system-instance"
                }
            ]
        }
    }
    logger.info("ORD well-known config requested")
    return JSONResponse(
        content=config,
        media_type="application/json;charset=UTF-8",
        headers={"Cache-Control": "max-age=300"}
    )


async def ord_document_system_version(request: Request) -> JSONResponse:
    try:
        base_url = os.environ.get("AGENT_PUBLIC_URL", str(request.base_url).rstrip("/"))
        document = load_ord_document(ORD_SYSTEM_VERSION_PATH)
        document = inject_base_url(document, base_url)
        logger.info("Serving ORD system-version document")
        return JSONResponse(
            content=document,
            media_type="application/json;charset=UTF-8",
            headers={"Cache-Control": "max-age=300"}
        )
    except Exception as e:
        logger.error(f"Error serving ORD system-version document: {e}")
        return JSONResponse(content={"error": "Failed to load ORD document"}, status_code=500)


def resolve_tenant_id(request: Request) -> str:
    return (
        request.query_params.get("local-tenant-id")
        or request.headers.get("local-tenant-id", "")
    )


async def ord_document_system_instance(request: Request) -> JSONResponse:
    try:
        base_url = os.environ.get("AGENT_PUBLIC_URL", str(request.base_url).rstrip("/"))
        local_tenant_id = resolve_tenant_id(request)
        document = load_ord_document(ORD_SYSTEM_INSTANCE_PATH)
        document = inject_base_url(document, base_url)
        doc_str = json.dumps(document)
        doc_str = doc_str.replace("{{LOCAL_TENANT_ID}}", local_tenant_id)
        document = json.loads(doc_str)
        logger.info(f"Serving ORD system-instance document, local_tenant_id={local_tenant_id!r}")
        return JSONResponse(
            content=document,
            media_type="application/json;charset=UTF-8",
            headers={"Cache-Control": "no-cache"}
        )
    except Exception as e:
        logger.error(f"Error serving ORD system-instance document: {e}")
        return JSONResponse(content={"error": "Failed to load ORD document"}, status_code=500)


def create_ord_routes() -> list:
    return [
        Route(
            "/.well-known/open-resource-discovery",
            well_known_ord_config,
            methods=["GET"],
            name="ord_config"
        ),
        Route(
            "/open-resource-discovery/v1/documents/system-version",
            ord_document_system_version,
            methods=["GET"],
            name="ord_document_system_version"
        ),
        Route(
            "/open-resource-discovery/v1/documents/system-instance",
            ord_document_system_instance,
            methods=["GET"],
            name="ord_document_system_instance"
        ),
    ]
