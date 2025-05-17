# agentverse-mcp-integration


A framework for building and deploying AI agents with Model Context Protocol (MCP) on the agentverse ecosystem.

## Overview

This library enables developers to:

1. **Build MCP Servers**: Create powerful MCP servers using the FastMCP pattern with decorator-based tool definitions
2. **Deploy on Agentverse**: Make your agents discoverable and accessible on the agentverse ecosystem
3. **ASI:One Integration**: Enable your agents to be discovered and used on ASI:One
4. **Claude Desktop Integration**: Connect your agents to Claude Desktop for seamless tool usage

## Key Features

- **FastMCP Pattern**: Simple decorator-based approach to defining tools
- **uAgent Integration**: Built on the uAgent framework for robust agent communication
- **Bridge & Proxy**: Complete solution for connecting Claude Desktop to your agents
- **Real API Integration**: Example implementation with National Weather Service API

## Installation

```bash
# Install from the local directory
pip install -e .
```

## Quick Start

### 1. Create Your FastMCP Server

```python
# server.py
from typing import Dict, Any

class FastMCP:
    def __init__(self, name):
        self.name = name
        self.tools = {}
    
    def tool(self):
        def decorator(func):
            # Tool registration logic
            self.tools[func.__name__] = {"func": func}
            return func
        return decorator

    async def list_tools(self):
        # Return list of tools
        return []
    
    async def call_tool(self, tool_name, args):
        # Call the requested tool
        return await self.tools[tool_name]["func"](**args)

# Initialize server
mcp = FastMCP("my_agent")

@mcp.tool()
async def hello_world(name: str) -> Dict[str, Any]:
    """Say hello to someone.
    
    name: Person's name
    """
    return {"message": f"Hello, {name}!"}
```

### 2. Create Your FastMCP Agent

```python
# agent.py
import os
import sys
import logging
from uagents import Agent

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uagent_mcp import FastMCPAdapter
from server import mcp

# Create agent
agent = Agent(name="my_agent", port=8003, mailbox=True)

# Create adapter
adapter = FastMCPAdapter(mcp_server=mcp, name="my_adapter")

# Register adapter with agent
adapter.register_with_agent(agent)

# Run agent
adapter.run(agent)
```

### 3. Set Up Bridge & Proxy for Claude Desktop

Use the provided bridge.py and new_proxy.py examples to connect your agent to Claude Desktop.

## Components

### Protocol Models

The library defines protocol models for MCP communication:

- `ListTools`: Request to list available tools
- `ListToolsResponse`: Response containing available tools or error
- `CallTool`: Request to call a specific tool with arguments
- `CallToolResponse`: Response from a tool call containing result or error

### FastMCP Server

The FastMCP server is the core component that defines tools using a decorator pattern:

```python
from typing import Dict, Any

# Initialize FastMCP server
mcp = FastMCP("weather")

@mcp.tool()
async def get_weather(location: str) -> Dict[str, Any]:
    """Get current weather for a location.
    
    location: City name or location
    """
    # Implementation to fetch weather data
    # ...
    return {
        "location": location,
        "temperature": 72,
        "condition": "Sunny"
    }
```

### FastMCP Adapter

The FastMCPAdapter connects your FastMCP server to the uAgent framework:

```python
from uagent_mcp import FastMCPAdapter
from uagents import Agent

# Create the agent
agent = Agent(
    name="weather_agent",
    port=8003,
    mailbox=True
)

# Create the adapter
adapter = FastMCPAdapter(mcp_server=mcp, name="weather_adapter")

# Register the adapter with the agent
adapter.register_with_agent(agent)

# Run the agent
adapter.run(agent)
```

### Bridge & Proxy

The bridge and proxy components connect Claude Desktop to your FastMCP agent:

```python
# In bridge.py
from uagent_mcp.protocol import ListTools, ListToolsResponse, CallTool, CallToolResponse

# Create the bridge
bridge = Bridge(
    agent_address="agent1qw2e3r4t5y6u7i8o9p0...",
    port=8080
)

# Start the JSON-RPC server
bridge.start_server()
```

```python
# In new_proxy.py
# Handle MCP handshake and format responses for Claude
proxy = Proxy(bridge_url="http://localhost:8080/jsonrpc")
proxy.start()
```

## Deployment & Integration

### Agentverse Deployment

To deploy your FastMCP agent on the agentverse ecosystem:

1. Package your FastMCP server and agent code
2. Deploy to a server with a public endpoint
3. Register your agent's address in the agentverse directory

```bash
# Example deployment command
python deploy_to_agentverse.py --agent-address agent1qw2e3r4t5y6u7i8o9p0... --endpoint https://your-server.com/agent
```

### ASI:One Integration

To make your agent discoverable on ASI:One:

1. Ensure your agent is deployed and accessible
2. Register your agent with ASI:One using the provided API
3. Include proper metadata and tool descriptions

```python
# Example ASI:One registration
from asi_one_client import ASIOneClient

client = ASIOneClient(api_key="your_api_key")
client.register_agent(
    agent_address="agent1qw2e3r4t5y6u7i8o9p0...",
    name="Weather Agent",
    description="Provides weather forecasts and alerts",
    tools=["get_weather", "get_forecast", "get_alerts"]
)
```

## Claude Desktop Configuration

To use the bridge with Claude Desktop, create a `claude_config.json` file:

```json
{
  "mcpServers": {
    "weather": {
      "command": "python3",
      "args": [
        "/Users/rajashekar/agents-agentverse/uagent_mcp/examples/new_proxy.py"
      ],
      "env": {
        "BRIDGE_URL": "http://localhost:8080/jsonrpc",
        "MCP_TIMEOUT": "12000"
      }
    }
  }
}

```

## License

MIT
