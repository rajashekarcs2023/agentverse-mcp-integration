# Weather Agent

## Description
This AI Agent provides comprehensive access to weather information through conversational interaction. It connects to the National Weather Service (NWS) API to deliver reliable forecasts, current conditions, and weather alerts for locations in the United States. Simply ask natural questions like "What's the weather in San Francisco today?" or "Are there any weather alerts in California?" to receive structured, detailed weather information. The agent combines AI-powered natural language understanding with direct access to weather data for travel planning and daily activities.

## Input Data Model

```python
class WeatherRequest(Model):
    request_type: str  # "current", "forecast", or "alerts"
    parameters: dict   # Contains location, coordinates, or state code
```

## Output Data Model

```python
class WeatherResponse(Model):
    results: str  # Formatted weather information
```

## Available Tools

### Get Weather
Retrieves the current weather conditions for a specified location.

**Parameters:**
- `location`: The city or location to get weather for (required)

**Example:**
```json
{
  "tool_name": "get_weather",
  "parameters": {
    "location": "San Francisco"
  }
}
```

### Get Forecast
Retrieves a weather forecast for a specified location using latitude and longitude.

**Parameters:**
- `latitude`: Latitude of the location (required)
- `longitude`: Longitude of the location (required)

**Example:**
```json
{
  "tool_name": "get_forecast",
  "parameters": {
    "latitude": 37.7749,
    "longitude": -122.4194
  }
}
```

### Get Alerts
Retrieves active weather alerts for a specified US state.

**Parameters:**
- `state`: Two-letter US state code (e.g., CA, NY) (required)

**Example:**
```json
{
  "tool_name": "get_alerts",
  "parameters": {
    "state": "CA"
  }
}
```

## Setup and Running

1. Make sure you have the required dependencies installed:
   ```
   pip install uagents httpx
   ```

2. Run the FastMCP agent:
   ```
   cd uagent_mcp/examples
   python fastmcp_agent.py
   ```

3. In a separate terminal, run the bridge:
   ```
   cd uagent_mcp/examples
   python bridge.py
   ```

## Integration with Claude Desktop

To use this agent with Claude Desktop:

1. Configure Claude Desktop with the following settings:
   - **BRIDGE_URL**: `http://localhost:8080/jsonrpc`
   - **MCP_TIMEOUT**: `12000`

2. Start a conversation with Claude and ask about the weather:
   - "What's the weather in San Francisco?"
   - "Get the forecast for latitude 37.7749 and longitude -122.4194"
   - "Are there any weather alerts in CA?"
