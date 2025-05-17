"""Adapter for connecting FastMCP servers to uAgents."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable, Awaitable
from uuid import uuid4

from uagents import Agent, Context, Model, Protocol
# Import chat protocol from the correct location
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)
from uagent_mcp.protocol import ListTools, ListToolsResponse, CallTool, CallToolResponse

logger = logging.getLogger(__name__)

def serialize_messages(messages: List[Dict[str, Any]]) -> str:
    """Serialize messages to JSON string."""
    return json.dumps(messages, default=str)


def deserialize_messages(messages_str: str) -> List[Dict[str, Any]]:
    """Deserialize messages from JSON string."""
    if not messages_str:
        return []
    return json.loads(messages_str)


class FastMCPAdapter:
    """Adapter for connecting FastMCP servers to uAgents."""
    
    def __init__(self, mcp_server: Any, name: str = "fastmcp_adapter"):
        """Initialize the adapter.
        
        Args:
            mcp_server: The FastMCP server instance
            name: Name for the adapter protocol
        """
        self.mcp_server = mcp_server
        self.name = name
        
        # Create protocols
        self.mcp_protocol = Protocol(name)
        # Use the name from the spec to avoid the warning
        self.chat_protocol = Protocol("AgentChatProtocol", spec=chat_protocol_spec)
        
        # Set up protocol handlers
        self.setup_mcp_protocol()
        self.setup_chat_protocol()
    
    def setup_mcp_protocol(self):
        """Set up the MCP protocol handlers."""
        
        @self.mcp_protocol.on_message(ListTools)
        async def handle_list_tools(ctx: Context, sender: str, msg: ListTools):
            """Handle ListTools requests."""
            logger.info(f"Received ListTools request from {sender} with id={msg.id}")
            try:
                # Get tools from the FastMCP server
                tools = await self.mcp_server.list_tools()
                
                # Send the response
                await ctx.send(
                    sender,
                    ListToolsResponse(
                        id=msg.id,
                        tools=tools,
                        error=None
                    )
                )
                logger.info(f"Sent ListToolsResponse to {sender} with {len(tools)} tools")
            except Exception as e:
                logger.error(f"Error listing tools: {str(e)}")
                await ctx.send(
                    sender,
                    ListToolsResponse(
                        id=msg.id,
                        tools=[],
                        error={"message": f"Error listing tools: {str(e)}"}
                    )
                )
        
        @self.mcp_protocol.on_message(CallTool)
        async def handle_call_tool(ctx: Context, sender: str, msg: CallTool):
            """Handle CallTool requests."""
            logger.info(f"Received CallTool request from {sender} for tool={msg.tool} with id={msg.id}")
            try:
                # Call the tool in the FastMCP server
                result = await self.mcp_server.call_tool(msg.tool, msg.arguments)
                
                # Send the response
                await ctx.send(
                    sender,
                    CallToolResponse(
                        id=msg.id,
                        result=result,
                        error=None
                    )
                )
                logger.info(f"Sent CallToolResponse to {sender} for tool={msg.tool}")
            except Exception as e:
                logger.error(f"Error calling tool {msg.tool}: {str(e)}")
                await ctx.send(
                    sender,
                    CallToolResponse(
                        id=msg.id,
                        result=None,
                        error={"message": f"Error: Failed to call tool {msg.tool}: {str(e)}"}
                    )
                )
                
    def setup_chat_protocol(self):
        """Set up the chat protocol handlers."""
        
        @self.chat_protocol.on_message(ChatMessage)
        async def handle_chat_message(ctx: Context, sender: str, msg: ChatMessage):
            # Send acknowledgement
            ack = ChatAcknowledgement(
                timestamp=datetime.now(timezone.utc),
                acknowledged_msg_id=msg.msg_id
            )
            await ctx.send(sender, ack)
            
            # Process each content item
            for item in msg.content:
                if isinstance(item, StartSessionContent):
                    logger.info(f"Got a start session message from {sender}")
                    continue
                elif isinstance(item, TextContent):
                    logger.info(f"Got a message from {sender}: {item.text}")
                    
                    try:
                        # Get available tools
                        tools = await self.mcp_server.list_tools()
                        
                        # Process the message with tools
                        user_query = item.text.strip()
                        
                        # Simple tool selection logic - find a tool that might handle this query
                        selected_tool = None
                        tool_args = {}
                        
                        message_text = item.text.lower()
                        
                        # Determine which tool to use based on the message
                        if "alerts" in message_text or "warnings" in message_text:
                            selected_tool = "get_alerts"
                            # Extract state code
                            state = None
                            if "in" in message_text:
                                state_text = message_text.split("in")[1].strip()
                                # Look for 2-letter state code
                                import re
                                state_match = re.search(r'\b([A-Za-z]{2})\b', state_text)
                                if state_match:
                                    state = state_match.group(1).upper()
                            
                            if not state:
                                state = "CA"  # Default to California
                            
                            tool_args = {"state": state}
                            
                        elif "forecast" in message_text or "coordinates" in message_text or "lat" in message_text:
                            selected_tool = "get_forecast"
                            # Extract latitude and longitude
                            import re
                            # Look for patterns like "latitude 37.7749 and longitude -122.4194" or "coordinates 40.7128, -74.0060"
                            coords = re.findall(r'(-?\d+\.\d+)', message_text)
                            
                            if len(coords) >= 2:
                                tool_args = {
                                    "latitude": float(coords[0]),
                                    "longitude": float(coords[1])
                                }
                            else:
                                # Default to San Francisco
                                tool_args = {
                                    "latitude": 37.7749,
                                    "longitude": -122.4194
                                }
                        else:
                            # Default to get_weather
                            selected_tool = "get_weather"
                            # Extract location after "in"
                            location = None
                            if "in" in message_text:
                                location = message_text.split("in")[1].strip()
                                if location.endswith("?"):
                                    location = location[:-1].strip()
                            if not location:
                                location = "San Francisco"
                            tool_args = {"location": location}
                        
                        if selected_tool:
                            try:
                                # Call the selected tool
                                logger.info(f"Calling tool '{selected_tool}' with arguments: {tool_args}")
                                result = await self.mcp_server.call_tool(selected_tool, tool_args)
                                
                                # Format the result as a response
                                if isinstance(result, dict):
                                    response_text = json.dumps(result, indent=2)
                                elif isinstance(result, list):
                                    response_text = "\n".join(str(r) for r in result)
                                else:
                                    response_text = str(result)
                                    
                                logger.info(f"Tool response: {response_text}")
                            except Exception as e:
                                logger.error(f"Error calling tool {selected_tool}: {str(e)}")
                                response_text = f"I encountered an error while trying to get the information: {str(e)}"
                        else:
                            response_text = "I'm sorry, I don't have a tool to handle that request."
                        
                        # Send the response back to the user
                        await ctx.send(
                            sender,
                            ChatMessage(
                                timestamp=datetime.now(timezone.utc),
                                msg_id=uuid4(),
                                content=[TextContent(type="text", text=response_text)]
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error processing chat message: {str(e)}")
                        await ctx.send(
                            sender,
                            ChatMessage(
                                timestamp=datetime.now(timezone.utc),
                                msg_id=uuid4(),
                                content=[TextContent(type="text", text=f"I encountered an error: {str(e)}")]
                            )
                        )
                else:
                    logger.info(f"Got unexpected content type from {sender}")
        
        @self.chat_protocol.on_message(ChatAcknowledgement)
        async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
            logger.info(f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}")
            if msg.metadata:
                logger.info(f"Metadata: {msg.metadata}")
    
    @property
    def protocols(self):
        """Get all protocols supported by this adapter."""
        return [self.mcp_protocol, self.chat_protocol]
    
    def register_with_agent(self, agent: Agent):
        """Register the adapter with a uAgent.
        
        Args:
            agent: The uAgent to register with
        """
        # Register both protocols with the agent
        # Use try-except to handle duplicate model registration
        for protocol in self.protocols:
            try:
                agent.include(protocol, publish_manifest=True)
            except RuntimeError as e:
                if "duplicate model" in str(e).lower():
                    logger.warning(f"Protocol {protocol.name} already registered with agent {agent.name}")
                else:
                    raise
        
        logger.info(f"Registered FastMCP adapter with agent {agent.name}")
    
    async def run_server(self):
        """Run the FastMCP server."""
        # This is a placeholder - FastMCP servers typically don't need to be "run"
        # But we could add initialization code here if needed
        pass
    
    def run(self, agent: Agent):
        """Run the adapter with the given agent.
        
        Args:
            agent: The uAgent to run with
        """
        # We don't need to register again here since it's already done in fastmcp_agent.py
        # Just start the agent
        agent.run()
