#!/usr/bin/env python3
"""Bridge for connecting to a uAgent MCP server."""

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import uuid
from typing import Dict, Any, Optional

from aiohttp import web
import aiohttp_cors

from uagents import Agent, Context, Model
from uagents.setup import fund_agent_if_low
from uagents.experimental.quota import QuotaProtocol

# We're using our own UAgentBridgeClient implementation instead of the library's UAgentClient
from uagent_mcp.protocol import ListTools, ListToolsResponse, CallTool, CallToolResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bridge.log"), logging.StreamHandler()]
)
logger = logging.getLogger("bridge")

# ========== UAGENT CLIENT SETUP =============

class UAgentBridgeClient:
    def __init__(self, target_address: str, port: int = 8082):
        self.target_address = target_address
        self.agent = Agent(
            name="bridge_client",
            port=port,
            mailbox=True
        )
        self.protocol = QuotaProtocol(
            storage_reference=self.agent.storage,
            name="Bridge-Protocol",
            version="0.1.0"
        )
        self.pending_futures = {}
        self._outgoing_queue = asyncio.Queue()
        self._setup_handlers()
        
        # Start the agent in a background thread
        def start_agent(agent):
            agent.run()
        threading.Thread(target=start_agent, args=(self.agent,), daemon=True).start()
        
        # Start a background task to process the outgoing queue
        asyncio.get_event_loop().create_task(self._process_outgoing_queue())

    def _setup_handlers(self):
        @self.protocol.on_message(ListToolsResponse)
        async def handle_list_tools_response(ctx: Context, sender: str, msg: ListToolsResponse):
            logger.info(f"Received ListToolsResponse for id={msg.id}")
            fut = self.pending_futures.pop(msg.id, None)
            if fut:
                fut.set_result({"success": True, "result": {"tools": msg.tools}, "error": msg.error})
            else:
                logger.warning(f"No pending future for id={msg.id}")
                
        @self.protocol.on_message(CallToolResponse)
        async def handle_call_tool_response(ctx: Context, sender: str, msg: CallToolResponse):
            logger.info(f"Received CallToolResponse for id={msg.id}")
            fut = self.pending_futures.pop(msg.id, None)
            if fut:
                fut.set_result({"success": msg.error is None, "result": msg.result, "error": msg.error})
            else:
                logger.warning(f"No pending future for id={msg.id}")
                
        @self.agent.on_interval(period=1.0)
        async def process_queue(ctx: Context):
            while not self._outgoing_queue.empty():
                target, req = await self._outgoing_queue.get()
                await ctx.send(target, req)
                
        self.agent.include(self.protocol, publish_manifest=True)

    async def _process_outgoing_queue(self):
        # Dummy coroutine to keep the event loop happy if not using on_interval
        while True:
            await asyncio.sleep(3600)

    async def call_tool(self, tool_name, parameters):
        req_id = str(uuid.uuid4())
        fut = asyncio.get_event_loop().create_future()
        self.pending_futures[req_id] = fut
        # Use 'arguments' instead of 'args' to match the expected format in the FastMCP server
        req = CallTool(id=req_id, tool=tool_name, arguments=parameters)
        await self._outgoing_queue.put((self.target_address, req))
        try:
            resp = await asyncio.wait_for(fut, timeout=90)
            return resp
        except Exception as e:
            self.pending_futures.pop(req_id, None)
            raise e
            
    async def list_tools(self):
        try:
            req_id = str(uuid.uuid4())
            fut = asyncio.get_event_loop().create_future()
            self.pending_futures[req_id] = fut
            req = ListTools(id=req_id)
            await self._outgoing_queue.put((self.target_address, req))
            resp = await asyncio.wait_for(fut, timeout=90)
            if resp["success"] and resp["result"] and isinstance(resp["result"], dict) and "tools" in resp["result"]:
                return resp["result"]["tools"]
            else:
                return []
        except Exception as e:
            logger.error(f"Error listing tools: {str(e)}")
            return []

# ========== HTTP SERVER =============
async def handle_jsonrpc(request):
    try:
        data = await request.json()
        logger.info(f"Received JSON-RPC: {data}")
        jsonrpc_id = data.get("id")
        method = data.get("method")
        params = data.get("params", {})

        # Forward all methods to uAgent
        if method == "tools/list":
            logger.info(f"[bridge] Received tools/list request")
            tools = await bridge_client.list_tools()
            logger.info(f"[bridge] Tools from agent: {tools}")
            response = {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"tools": tools}
            }
            logger.info(f"[bridge] Sending tools/list response: {response}")
            return web.json_response(response)
        elif method == "tools/call":
            tool_name = params.get("name")
            # Use 'arguments' instead of 'args' to match the JSON-RPC request format
            tool_args = params.get("arguments", {})
            logger.info(f"[bridge] Calling tool '{tool_name}' with arguments: {tool_args}")
            resp = await bridge_client.call_tool(tool_name, tool_args)
            logger.info(f"[bridge] Called tool '{tool_name}' with arguments: {tool_args}")
        else:
            resp = await bridge_client.call_tool(method, params)
            
        logger.info(f"[bridge] Received from uAgent: {resp}")
        
        if resp["success"]:
            result = resp["result"]
            error = None
        else:
            result = None
            error = resp["error"] or "Unknown error"
            
        response = {
            "jsonrpc": "2.0",
            "id": jsonrpc_id,
            "result": result
        }
        
        if error:
            response = {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "error": {"code": -32000, "message": error}
            }
            
        logger.info(f"[bridge] Sending HTTP response to proxy: {response}")
        return web.json_response(response, dumps=lambda x: json.dumps(x, ensure_ascii=False))
    except Exception as e:
        logger.exception("Error in handle_jsonrpc")
        return web.json_response(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(e)}}, 
            status=500
        )

def main():
    """Main function to run the bridge."""
    parser = argparse.ArgumentParser(description="uAgent MCP Bridge")
    parser.add_argument("--agent-address", type=str, default="agent1qw9r2800a7qvkk9ffuuap34qvlz9fg4ez8lj5ffml9rqkkjqezmyxtt2qf7", help="Address of the MCP server uAgent")
    parser.add_argument("--port", type=int, default=8080, help="Port for the bridge HTTP server")
    parser.add_argument("--client-port", type=int, default=8082, help="Port for the client agent")
    args = parser.parse_args()
    
    # Hardcoded agent address
    agent_address = "agent1qtqp9dryh98fzv0zgrsglkhahv796upk0f0vxh6rnu6qd73wtkh5zetkrm6"  # FastMCP Weather agent address
    logger.info(f"Using hardcoded agent address: {agent_address}")
    
    # Get port from args or environment
    port = args.port or int(os.environ.get("BRIDGE_PORT", "8080"))
    
    # Create the bridge client
    client_port = args.client_port or int(os.environ.get("CLIENT_AGENT_PORT", "8082"))
    global bridge_client
    bridge_client = UAgentBridgeClient(agent_address, port=client_port)
    
    # Create the web app
    app = web.Application()
    app.router.add_post("/jsonrpc", handle_jsonrpc)
    
    # Add CORS support
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    for route in list(app.router.routes()):
        cors.add(route)
    
    # Run the web app
    logger.info(f"Starting bridge on port {port}")
    web.run_app(app, port=port)

if __name__ == "__main__":
    main()
