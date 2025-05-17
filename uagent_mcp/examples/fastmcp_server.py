"""FastMCP server with weather tools."""

from typing import Any, Dict, List, Optional
import httpx
import asyncio

class FastMCP:
    """FastMCP server with weather tools."""
    
    def __init__(self, name: str):
        """Initialize the FastMCP server."""
        self.name = name
        self.tools = {}
    
    def tool(self):
        """Decorator to register a tool."""
        def decorator(func):
            import inspect
            signature = inspect.signature(func)
            parameters = {}
            required = []
            
            for name, param in signature.parameters.items():
                param_type = param.annotation
                if param_type is inspect.Parameter.empty:
                    param_type = str
                
                if param_type is int:
                    param_schema = {"type": "integer"}
                elif param_type is float:
                    param_schema = {"type": "number"}
                elif param_type is bool:
                    param_schema = {"type": "boolean"}
                else:
                    param_schema = {"type": "string"}
                
                # Add description if available from docstring
                if func.__doc__:
                    for line in func.__doc__.split("\n"):
                        line = line.strip()
                        if line.startswith(f"{name}:"):
                            param_schema["description"] = line[len(name)+1:].strip()
                
                parameters[name] = param_schema
                if param.default is inspect.Parameter.empty:
                    required.append(name)
            
            # Create tool schema
            tool_schema = {
                "name": func.__name__,
                "description": func.__doc__.split("\n")[0] if func.__doc__ else "",
                "inputSchema": {
                    "type": "object",
                    "properties": parameters,
                    "required": required
                }
            }
            
            self.tools[func.__name__] = {
                "schema": tool_schema,
                "func": func
            }
            return func
        return decorator
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools."""
        return [tool["schema"] for tool in self.tools.values()]
    
    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Call a tool by name with arguments."""
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        tool = self.tools[tool_name]
        return await tool["func"](**args)


# Initialize FastMCP server
mcp = FastMCP("weather")

# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"

async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error making NWS request: {str(e)}")
            return None

def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
Event: {props.get('event', 'Unknown')}
Area: {props.get('areaDesc', 'Unknown')}
Severity: {props.get('severity', 'Unknown')}
Description: {props.get('description', 'No description available')}
Instructions: {props.get('instruction', 'No specific instructions provided')}
"""

@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state.
    
    state: Two-letter US state code (e.g. CA, NY)
    """
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)

@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a location.
    
    latitude: Latitude of the location
    longitude: Longitude of the location
    """
    # First get the forecast grid endpoint
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)

    if not points_data:
        return "Unable to fetch forecast data for this location."

    # Get the forecast URL from the points response
    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)

    if not forecast_data:
        return "Unable to fetch detailed forecast."

    # Format the periods into a readable forecast
    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:  # Only show next 5 periods
        forecast = f"""
{period['name']}:
Temperature: {period['temperature']}°{period['temperatureUnit']}
Wind: {period['windSpeed']} {period['windDirection']}
Forecast: {period['detailedForecast']}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)

@mcp.tool()
async def get_weather(location: str) -> Dict[str, Any]:
    """Get current weather for a location.
    
    location: City name or location
    """
    # For simplicity, we'll use simulated data for locations since the NWS API requires lat/lon
    # In a real implementation, you would use geocoding to convert location to lat/lon
    weather_conditions = ["Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Thunderstorms"]
    wind_directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    
    # Use location to seed the random generator for consistent results
    import hashlib
    seed = int(hashlib.md5(location.encode()).hexdigest(), 16) % 10000
    import random
    rng = random.Random(seed)
    
    temperature = rng.randint(50, 85)
    condition = rng.choice(weather_conditions)
    humidity = rng.randint(30, 90)
    wind_speed = rng.randint(0, 20)
    wind_direction = rng.choice(wind_directions)
    
    return {
        "location": location,
        "temperature": temperature,
        "condition": condition,
        "humidity": humidity,
        "wind": {
            "speed": wind_speed,
            "direction": wind_direction
        }
    }
