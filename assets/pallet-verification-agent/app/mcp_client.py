"""MCP Client for Agent Gateway Integration via mTLS."""

import json
import logging
import os
import tempfile
from dataclasses import dataclass

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)

MCP_ENDPOINT_PATH = "/v1/mcp/sap.mcpbuilder:apiResource:cost-center:v1/730297600"
AGW_RESOURCE_NAME = "agent-gateway"
UMS_CREDENTIALS_PATH = "/etc/ums/credentials/credentials"


@dataclass
class AgwCredentials:
    auth_type: str
    certificate: str
    client_id: str
    expires_at: str
    gateway_url: str
    private_key: str
    token_service_url: str
    uri: str

    @classmethod
    def from_dict(cls, data: dict) -> "AgwCredentials":
        return cls(
            auth_type=data.get("authType", ""),
            certificate=data.get("certificate", ""),
            client_id=data.get("clientid", ""),
            expires_at=data.get("expiresAt", ""),
            gateway_url=data.get("gatewayUrl", ""),
            private_key=data.get("privateKey", ""),
            token_service_url=data.get("tokenServiceUrl", ""),
            uri=data.get("uri", ""),
        )

    @property
    def mcp_url(self) -> str:
        return f"{self.gateway_url.rstrip('/')}{MCP_ENDPOINT_PATH}"


@dataclass
class MCPTool:
    name: str
    server_name: str
    description: str
    input_schema: dict
    url: str

    @property
    def namespaced_name(self) -> str:
        return f"{self.server_name}__{self.name}"


def load_agw_credentials() -> AgwCredentials | None:
    data = None
    if os.path.exists(UMS_CREDENTIALS_PATH):
        try:
            with open(UMS_CREDENTIALS_PATH) as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to read credentials: %s", e)
            return None

    if data is None:
        credentials_json = os.environ.get("AGW_CREDENTIALS_JSON", "")
        if credentials_json:
            try:
                data = json.loads(credentials_json)
            except Exception as e:
                logger.error("Failed to parse AGW_CREDENTIALS_JSON: %s", e)
                return None

    if data is None:
        logger.info("No AGW credentials found - MCP tools will not be available")
        return None

    try:
        creds = AgwCredentials.from_dict(data)
        if not creds.gateway_url or not creds.client_id:
            logger.warning("AGW credentials missing required fields")
            return None
        if not creds.certificate or not creds.private_key or not creds.token_service_url:
            logger.warning("AGW mTLS credentials incomplete")
            return None
        logger.info("Loaded AGW credentials for client_id: %s...", creds.client_id[:8])
        return creds
    except Exception as e:
        logger.error("Failed to load AGW credentials: %s", e)
        return None


async def get_oauth_token(credentials: AgwCredentials) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as cf:
        cf.write(credentials.certificate)
        cert_path = cf.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as kf:
        kf.write(credentials.private_key)
        key_path = kf.name
    try:
        async with httpx.AsyncClient(cert=(cert_path, key_path), timeout=30.0) as client:
            response = await client.post(
                credentials.token_service_url,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                data={
                    "client_id": credentials.client_id,
                    "grant_type": "client_credentials",
                    "resource": f"urn:sap:identity:application:provider:name:{AGW_RESOURCE_NAME}",
                },
            )
            response.raise_for_status()
            access_token = response.json().get("access_token")
            if not access_token:
                raise ValueError("No access_token in response")
            return f"Bearer {access_token}"
    finally:
        for p in (cert_path, key_path):
            try:
                os.unlink(p)
            except Exception:
                pass


class MCPClient:
    def __init__(self, credentials: AgwCredentials | None = None):
        self.credentials = credentials or load_agw_credentials()

    async def _get_auth_header(self) -> str:
        if not self.credentials:
            raise ValueError("No AGW credentials available")
        return await get_oauth_token(self.credentials)

    async def get_mcp_tools(self) -> list[MCPTool]:
        if not self.credentials:
            logger.warning("No AGW credentials - skipping MCP tool discovery")
            return []
        try:
            auth_header = await self._get_auth_header()
            async with httpx.AsyncClient(headers={"Authorization": auth_header}, timeout=30.0) as http_client:
                async with streamable_http_client(self.credentials.mcp_url, http_client=http_client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        init_result = await session.initialize()
                        server_name = (
                            init_result.serverInfo.name
                            if init_result and init_result.serverInfo and init_result.serverInfo.name
                            else "agent-gateway"
                        )
                        result = await session.list_tools()
                        return [
                            MCPTool(
                                name=t.name,
                                server_name=server_name,
                                description=t.description or "",
                                input_schema=t.inputSchema or {},
                                url=self.credentials.mcp_url,
                            )
                            for t in result.tools
                        ]
        except Exception:
            logger.exception("Failed to discover MCP tools")
            return []

    async def call_tool(self, tool: MCPTool, **kwargs) -> str:
        if not self.credentials:
            raise ValueError("No AGW credentials available")
        auth_header = await self._get_auth_header()
        async with httpx.AsyncClient(headers={"Authorization": auth_header}, timeout=60.0) as http_client:
            async with streamable_http_client(tool.url, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool.name, kwargs)
                    return str(result.content[0].text if result.content else "")


class MCPToolConverter:
    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client

    def to_langchain(self, mcp_tool: MCPTool):
        from langchain_core.tools import StructuredTool
        from pydantic import create_model

        mcp_client = self.mcp_client
        properties = mcp_tool.input_schema.get("properties", {})
        required = set(mcp_tool.input_schema.get("required", []))
        fields = {}
        for name, prop in properties.items():
            prop_type = prop.get("type", "string")
            python_type = {"integer": int, "number": float, "boolean": bool}.get(prop_type, str)
            if name in required:
                fields[name] = (python_type, ...)
            else:
                fields[name] = (python_type | None, None)

        args_schema = create_model(f"{mcp_tool.name}_args", **fields) if fields else None

        async def run(**kwargs) -> str:
            return await mcp_client.call_tool(mcp_tool, **kwargs)

        return StructuredTool.from_function(
            coroutine=run,
            name=mcp_tool.name,
            description=mcp_tool.description,
            args_schema=args_schema,
        )
