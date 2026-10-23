"""Local MCP protocol fixture used by the integration tests."""
from typing import Literal
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

server = FastMCP("research-test")

class Options(BaseModel):
    mode: Literal["brief", "full"]
    count: int = Field(ge=1, le=5)

@server.tool()
def inspect_evidence(options: Options) -> dict:
    """Return nested validated options for adapter integration testing."""
    return {"mode":options.mode,"count":options.count,"source":"local test fixture"}

if __name__ == "__main__":
    server.run(transport="stdio")
