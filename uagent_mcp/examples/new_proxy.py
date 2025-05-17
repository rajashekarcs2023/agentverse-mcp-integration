import sys
import requests
import os
import json

# Get the bridge URL from env or default to localhost
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://localhost:8080/jsonrpc")
MCP_TIMEOUT = int(os.environ.get("MCP_TIMEOUT", "120"))

# Define the weather tools array for reuse
WEATHER_TOOLS = [
    {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name or location"}
            },
            "required": ["location"]
        }
    },
    {
        "name": "get_forecast",
        "description": "Get weather forecast for a location",
        "inputSchema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Latitude of the location"},
                "longitude": {"type": "number", "description": "Longitude of the location"}
            },
            "required": ["latitude", "longitude"]
        }
    },
    {
        "name": "get_alerts",
        "description": "Get weather alerts for a US state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "Two-letter US state code (e.g. CA, NY)"}
            },
            "required": ["state"]
        }
    }
]

def handle_initialize(request):
    # Respond with a fully MCP-compliant initialize response (official format)
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": {
            "protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
            "capabilities": {
                "tools": {tool["name"]: tool for tool in WEATHER_TOOLS}
            },
            "serverInfo": {
                "name": "weather",
                "version": "0.1.0"
            }
        }
    }

def handle_tools_list(request):
    # Return the weather tools array in official MCP format
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": {"tools": WEATHER_TOOLS}
    }

def handle_resources_list(request):
    # Return empty resources
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": {"resources": []}
    }

def handle_prompts_list(request):
    # Return empty prompts
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": {"prompts": []}
    }

# Add more handshake methods here as needed
HANDSHAKE_METHODS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "resources/list": handle_resources_list,
    "prompts/list": handle_prompts_list,
}

def main():
    print(f"[proxy] Proxy started. Bridge URL: {BRIDGE_URL}", file=sys.stderr)
    
    while True:
        try:
            # Read a line from stdin
            line = sys.stdin.readline()
            print(f"[proxy] Received from stdin: {line.strip()}", file=sys.stderr)
            
            if not line:
                break
                
            # Parse the JSON-RPC request
            req = json.loads(line)
            method = req.get("method")
            
            # Handle handshake methods locally
            if method in HANDSHAKE_METHODS:
                if "id" in req:
                    resp = HANDSHAKE_METHODS[method](req)
                    print(f"[proxy] Handshake method '{method}' handled locally.", file=sys.stderr)
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            # Ignore notifications
            elif method and method.startswith("notifications/"):
                print(f"[proxy] Notification '{method}' ignored.", file=sys.stderr)
                continue
            # Forward everything else to the bridge
            else:
                print(f"[proxy] Forwarding method '{method}' to bridge.", file=sys.stderr)
                try:
                    print(f"[proxy] Sending HTTP POST to bridge: {BRIDGE_URL} with payload: {line.strip()}", file=sys.stderr)
                    r = requests.post(BRIDGE_URL, data=line, headers={"Content-Type": "application/json"}, timeout=MCP_TIMEOUT)
                    print(f"[proxy] Received HTTP response: Status {r.status_code}, Body: {r.text}", file=sys.stderr)
                    
                    if "id" in req:
                        # Parse the response
                        resp_json = json.loads(r.text)
                        
                        # Check if this is a tool call response
                        if method == "tools/call":
                            # Format the response in a way Claude can understand
                            print(f"[proxy] Formatting tool response for Claude", file=sys.stderr)
                            
                            # Format according to MCP protocol
                            if "result" in resp_json:
                                # Success case
                                tool_name = req["params"]["name"]
                                formatted_resp = {
                                    "jsonrpc": "2.0",
                                    "id": req["id"],
                                    "result": {
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": json.dumps(resp_json["result"])
                                            }
                                        ]
                                    }
                                }
                            elif "error" in resp_json:
                                # Error case
                                formatted_resp = {
                                    "jsonrpc": "2.0",
                                    "id": req["id"],
                                    "error": resp_json["error"]
                                }
                            
                            print(f"[proxy] Writing formatted response to stdout: {formatted_resp}", file=sys.stderr)
                            sys.stdout.write(json.dumps(formatted_resp) + "\n")
                        else:
                            # For non-tool responses, pass through unchanged
                            print(f"[proxy] Writing to stdout: {r.text}", file=sys.stderr)
                            sys.stdout.write(r.text + "\n")
                        
                        sys.stdout.flush()
                except requests.Timeout:
                    if "id" in req:
                        sys.stdout.write(json.dumps({
                            "jsonrpc": "2.0",
                            "id": req["id"],
                            "error": {
                                "code": -32001,
                                "message": "Bridge request timed out"
                            }
                        }) + "\n")
                        sys.stdout.flush()
        except Exception as e:
            print(f"[proxy] Exception: {str(e)}", file=sys.stderr)
            try:
                req = json.loads(line)
                if "id" in req:
                    sys.stdout.write(json.dumps({
                        "jsonrpc": "2.0",
                        "id": req["id"],
                        "error": {
                            "code": -32000,
                            "message": f"Proxy error: {str(e)}"
                        }
                    }) + "\n")
                    sys.stdout.flush()
            except Exception as e2:
                print(f"[proxy] Exception in error handler: {str(e2)}", file=sys.stderr)

if __name__ == "__main__":
    main()
