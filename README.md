# agentverse-mcp-integration
# uAgent MCP

A library for integrating uAgents with Model Control Protocol (MCP) servers.

## Overview

This library provides a simple way to:

1. Create MCP servers that expose tools via uAgents
2. Create clients that can communicate with MCP servers via uAgents
3. Build bridges and proxies for connecting Claude Desktop to MCP servers

## Installation

```bash
# Install from the local directory
pip install -e .
```

## Components

### Protocol Models

The library defines protocol models for MCP communication:

- `ListTools`: Request to list available tools
- `ListToolsResponse`: Response containing available tools or error
- `CallTool`: Request to call a specific tool with arguments
- `CallToolResponse`: Response from a tool call containing result or error

### Client

The `UAgentClient` class provides a client for communicating with FastMCP agents:

```python
from uagent_mcp import UAgentClient

client = UAgentClient(
    target_address="agent1q...",
    port=9001,
    target_endpoint="http://localhost:8000/uagents"
)

# List tools
tools = await client.list_tools()

# Call a tool
result = client.call_tool("get_weather", {"location": "San Francisco"})
```

## Example: Weather Agent

The library includes an example weather agent that demonstrates how to use the `MCPServerAdapter` class to expose weather tools via uAgents.

```python
# Create the weather tools
weather_tools = WeatherTools()

# Create the agent
agent = Agent(
    name="weather-agent",
    seed="weather-agent-seed",
    endpoint=["http://127.0.0.1:8000/submit"],
    port=8000,
)

# Create the MCP adapter
adapter = MCPServerAdapter(
    mcp_server=weather_tools,
    asi1_api_key=os.environ.get("ASI1_API_KEY"),
    model="claude-3-haiku-20240307"
)

# Register protocols
for protocol in adapter.protocols:
    agent.include(protocol)

# Run the agent with the MCP adapter
adapter.run(agent, transport=os.environ.get("MCP_TRANSPORT"))
```

## Example: Claude Desktop Bridge

The library includes an example bridge script that connects Claude Desktop to a uAgent MCP server.

```python
# Create the bridge
bridge = ClaudeBridge(
    agent_address="agent1qw2e3r4t5y6u7i8o9p0...",
    timeout=30
)

# Start the bridge
bridge.start()

# Process stdin/stdout communication with Claude Desktop
while True:
    # Read a line from stdin
    line = sys.stdin.readline()
    if not line:
        break
    
    # Parse the JSON-RPC request
    request = json.loads(line)
    
    # Handle the request
    response = bridge.handle_request(request)
    
    # Send the response to stdout
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()
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
