"""uAgent MCP - A library for integrating uAgents with MCP servers."""

from .protocol import ListTools, ListToolsResponse, CallTool, CallToolResponse
from .fastmcp_adapter import FastMCPAdapter

__version__ = "0.1.0"
__all__ = [
    "ListTools", 
    "ListToolsResponse", 
    "CallTool", 
    "CallToolResponse",
    "FastMCPAdapter"
]
