"""Protocol definitions for MCP (Model Control Protocol) with uAgents."""

from typing import Any, Dict, List, Optional

from uagents import Model


class ListTools(Model):
    """Request to list available tools."""
    protocol: str = "mcp"
    type: str = "list_tools"
    id: str


class ListToolsResponse(Model):
    """Response containing available tools or error."""
    protocol: str = "mcp"
    type: str = "list_tools_response"
    id: str
    tools: List[Dict[str, Any]] = []
    error: Optional[Dict[str, Any]] = None


class CallTool(Model):
    """Request to call a specific tool with arguments."""
    protocol: str = "mcp"
    type: str = "call_tool"
    id: str
    tool: str
    arguments: Dict[str, Any] = {}


class CallToolResponse(Model):
    """Response from a tool call containing result or error."""
    protocol: str = "mcp"
    type: str = "call_tool_response"
    id: str
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
