"""Optional MCP adapters. Configuration is explicit, local and read on each run."""
from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import jsonschema
from langchain_core.tools import StructuredTool


@asynccontextmanager
async def connection(config):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client
    if config.get("transport", "stdio") == "stdio":
        params = StdioServerParameters(command=config["command"], args=config.get("args", []),
                                       env=config.get("env"), cwd=config.get("cwd"))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                yield session
    elif config["transport"] == "streamable_http":
        async with httpx.AsyncClient(headers=config.get("headers", {}), timeout=45) as client:
            async with streamable_http_client(config["url"], http_client=client) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    yield session
    else:
        raise ValueError("Supported MCP transports: stdio, streamable_http")


def make_tool(server_name, config, info):
    schema = info.inputSchema
    name = "mcp_" + server_name + "_" + info.name
    if len(name) > 64 or not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise ValueError("MCP names must form a unique tool name <=64 characters")

    async def invoke(**kwargs):
        jsonschema.validate(kwargs, schema)
        async with connection(config) as session:
            result = await session.call_tool(info.name, kwargs)
            blocks = [c.model_dump(mode="json") for c in result.content]
            # Binary resources are represented by metadata; do not flood LLM context with base64.
            for block in blocks:
                if "data" in block:
                    block["data"] = "[binary content omitted]"
            return {"ok": not result.isError, "server": server_name, "content": blocks,
                    "structured_content": getattr(result, "structuredContent", None)}

    return StructuredTool(name=name, description=info.description or f"MCP tool {info.name}",
                          args_schema=schema, coroutine=invoke)


async def load_tools(path: Path):
    if not path.exists():
        return [], []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    tools, errors = [], []
    for name, config in data.get("mcpServers", {}).items():
        if config.get("disabled", False):
            continue
        try:
            async def discover():
                async with connection(config) as session:
                    found, cursor = [], None
                    for _ in range(20):
                        result = await session.list_tools(cursor=cursor)
                        found.extend(result.tools)
                        cursor = result.nextCursor
                        if not cursor:
                            break
                    return found
            infos = await asyncio.wait_for(discover(), timeout=30)
            allowed = config.get("allowed_tools")
            tools.extend(make_tool(name, config, info) for info in infos if allowed is None or info.name in allowed)
        except Exception as exc:
            # Some SDK errors include endpoint headers. Expose only type, never config.
            errors.append({"server": name, "error": type(exc).__name__})
    return tools, errors
