"""Adapter for connecting FastMCP servers to uAgents.

This module provides adapters for connecting FastMCP servers to uAgents,
with support for both Claude Desktop integration via bridge/proxy and
direct ASI1 API integration.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    StartSessionContent,
    TextContent,
    EndSessionContent,
    chat_protocol_spec,
)

from .protocol import (
    CallTool,
    CallToolResponse,
    ListTools,
    ListToolsResponse,
)

# Define ASI1 API constants
ASI1_BASE_URL = "https://api.asi1.ai/v1"

# Set up logging
logger = logging.getLogger(__name__)

# Define MCP protocol spec (since it's missing from the protocol module)
mcp_protocol_spec = {
    "protocol": "mcp",
    "messages": [
        {
            "name": "ListTools",
            "schema": {
                "type": "object",
                "properties": {
                    "protocol": {"type": "string", "const": "mcp"},
                    "type": {"type": "string", "const": "list_tools"},
                    "id": {"type": "string"}
                },
                "required": ["protocol", "type", "id"]
            }
        },
        {
            "name": "ListToolsResponse",
            "schema": {
                "type": "object",
                "properties": {
                    "protocol": {"type": "string", "const": "mcp"},
                    "type": {"type": "string", "const": "list_tools_response"},
                    "id": {"type": "string"},
                    "tools": {"type": "array", "items": {"type": "object"}},
                    "error": {"type": ["object", "null"]}
                },
                "required": ["protocol", "type", "id", "tools"]
            }
        },
        {
            "name": "CallTool",
            "schema": {
                "type": "object",
                "properties": {
                    "protocol": {"type": "string", "const": "mcp"},
                    "type": {"type": "string", "const": "call_tool"},
                    "id": {"type": "string"},
                    "tool": {"type": "string"},
                    "arguments": {"type": "object"}
                },
                "required": ["protocol", "type", "id", "tool"]
            }
        },
        {
            "name": "CallToolResponse",
            "schema": {
                "type": "object",
                "properties": {
                    "protocol": {"type": "string", "const": "mcp"},
                    "type": {"type": "string", "const": "call_tool_response"},
                    "id": {"type": "string"},
                    "result": {"type": ["object", "string", "number", "array", "boolean", "null"]},
                    "error": {"type": ["object", "null"]}
                },
                "required": ["protocol", "type", "id"]
            }
        }
    ]
}


def serialize_messages(messages: List[Dict[str, Any]]) -> str:
    """Serialize messages to JSON string."""
    return json.dumps(messages, default=str)


def deserialize_messages(messages_str: str) -> List[Dict[str, Any]]:
    """Deserialize messages from JSON string."""
    if not messages_str:
        return []
    return json.loads(messages_str)


class FastMCPAdapter:
    """Adapter for connecting FastMCP servers to uAgents.
    
    This adapter supports three modes of operation:
    1. Bridge mode: For connecting to Claude Desktop via bridge and proxy
    2. ASI1 mode: For direct integration with ASI1 API
    3. Dual mode: Supports both bridge and ASI1 modes simultaneously
    
    The mode is automatically determined based on whether ASI1 API key and model
    are provided during initialization, and whether dual_mode is set to True.
    """
    
    def __init__(
        self,
        mcp_server: Any,
        name: str = "fastmcp_adapter",
        asi1_api_key: Optional[str] = None,
        model: Optional[str] = None,
        asi1_base_url: str = ASI1_BASE_URL,
        dual_mode: bool = True,  # Always use dual mode by default
    ):
        """
        Initialize the adapter.
        
        Args:
            mcp_server: The FastMCP server instance
            name: Name for the adapter protocol (used in bridge mode)
            asi1_api_key: Optional API key for ASI1 integration
            model: Optional model name for ASI1 integration
            asi1_base_url: Base URL for ASI1 API (default: "https://api.asi1.ai/v1")
            dual_mode: Whether to support both ASI1 and bridge modes simultaneously
        """
        self.mcp_server = mcp_server
        self.name = name
        self.asi1_api_key = asi1_api_key
        self.model = model
        self.asi1_base_url = asi1_base_url
        self.dual_mode = dual_mode
        
        # Determine the mode based on inputs
        self.asi1_mode = asi1_api_key is not None and model is not None
        self.bridge_mode = True  # Always enable bridge mode by default
        self.dual_mode = dual_mode  # Store the dual_mode setting
        
        # Create protocols based on the mode
        if self.dual_mode:
            # In dual mode, create both sets of protocols
            # For ASI1 mode, we need to provide a name since the Protocol class expects it
            self.asi1_mcp_protocol = Protocol(name="MCPProtocol", version="1.0.0", role="server")
            self.asi1_chat_protocol = Protocol(name="AgentChatProtocol", version="0.3.0", spec=chat_protocol_spec)
            
            self.bridge_mcp_protocol = Protocol(name)
            self.bridge_chat_protocol = Protocol("AgentChatProtocol", spec=chat_protocol_spec)
            
            # Set the default protocols to the bridge ones
            self.mcp_protocol = self.bridge_mcp_protocol
            self.chat_protocol = self.bridge_chat_protocol
            
            logger.info("Initialized FastMCPAdapter in dual mode (both ASI1 and bridge)")
        elif self.asi1_mode:
            # In ASI1-only mode, use the protocol specs with server role
            self.mcp_protocol = Protocol(name="MCPProtocol", version="1.0.0", role="server")
            self.chat_protocol = Protocol(name="AgentChatProtocol", version="0.3.0", spec=chat_protocol_spec)
            logger.info("Initialized FastMCPAdapter in ASI1 mode")
        else:
            # In bridge-only mode, use the simple protocol initialization
            self.mcp_protocol = Protocol(name)
            self.chat_protocol = Protocol("AgentChatProtocol", spec=chat_protocol_spec)
            logger.info("Initialized FastMCPAdapter in bridge mode")
        
        # Set up protocol handlers
        self._setup_mcp_protocol_handlers()
        self._setup_chat_protocol_handlers()
    
    @property
    def protocols(self) -> list[Protocol]:
        """Get the protocols supported by this adapter."""
        if self.dual_mode and self.asi1_mode:
            return [self.bridge_mcp_protocol, self.bridge_chat_protocol, 
                    self.asi1_mcp_protocol, self.asi1_chat_protocol]
        else:
            return [self.mcp_protocol, self.chat_protocol]
    
    def _setup_mcp_protocol_handlers(self):
        """Set up handlers for MCP protocol messages."""
        
        async def handle_list_tools_impl(ctx: Context, sender: str, msg: ListTools):
            """Implementation of ListTools handler."""
            ctx.logger.info(f"Received ListTools request from {sender}")
            try:
                # Get tools from the FastMCP server
                tools = await self.mcp_server.list_tools()
                
                # Log tool information
                for tool in tools:
                    # Handle both object-style and dict-style tools
                    tool_name = tool.name if hasattr(tool, 'name') else tool.get('name', '')
                    tool_desc = tool.description if hasattr(tool, 'description') else tool.get('description', '')
                    tool_schema = tool.inputSchema if hasattr(tool, 'inputSchema') else tool.get('inputSchema', {})
                    
                    ctx.logger.info(f"Tool Name: {tool_name}")
                    ctx.logger.info(f"Description: {tool_desc}")
                    ctx.logger.info(f"Parameters: {json.dumps(tool_schema, indent=2)}")
                
                # Format tools for response
                raw_tools = []
                for tool in tools:
                    # Handle both object-style and dict-style tools
                    if hasattr(tool, 'name'):
                        # Object-style tool
                        raw_tools.append({
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema
                        })
                    else:
                        # Dict-style tool
                        raw_tools.append(tool)
                
                # Send the response
                await ctx.send(
                    sender,
                    ListToolsResponse(
                        id=msg.id,  # Include the id from the request
                        tools=raw_tools,
                        error=None
                    )
                )
                ctx.logger.info(f"Sent ListToolsResponse to {sender} with {len(raw_tools)} tools")
            except Exception as e:
                error_msg = "Error: Failed to retrieve tools from MCP Server"
                ctx.logger.error(f"{error_msg}: {str(e)}")
                await ctx.send(
                    sender,
                    ListToolsResponse(
                        id=msg.id,  # Include the id from the request
                        tools=[],
                        error={"message": error_msg}
                    )
                )
        
        # Register the handler with the appropriate protocol(s)
        if self.dual_mode and self.asi1_mode:
            # In dual mode, register with both protocol sets
            @self.bridge_mcp_protocol.on_message(model=ListTools)
            async def handle_bridge_list_tools(ctx: Context, sender: str, msg: ListTools):
                await handle_list_tools_impl(ctx, sender, msg)
                
            @self.asi1_mcp_protocol.on_message(model=ListTools)
            async def handle_asi1_list_tools(ctx: Context, sender: str, msg: ListTools):
                await handle_list_tools_impl(ctx, sender, msg)
        else:
            # In single mode, register with the active protocol
            @self.mcp_protocol.on_message(model=ListTools)
            async def handle_list_tools(ctx: Context, sender: str, msg: ListTools):
                await handle_list_tools_impl(ctx, sender, msg)
        
        async def handle_call_tool_impl(ctx: Context, sender: str, msg: CallTool):
            """Implementation of CallTool handler."""
            ctx.logger.info(f"Calling tool: {msg.tool} with args: {msg.arguments}")
            try:
                # Call the tool in the FastMCP server
                output = await self.mcp_server.call_tool(msg.tool, msg.arguments)
                
                # Format the result
                result = "\n".join(str(r) for r in output) if isinstance(output, list) else str(output)
                
                # Send the response
                await ctx.send(
                    sender,
                    CallToolResponse(
                        id=msg.id,  # Include the id from the request
                        result=result,
                        error=None
                    )
                )
                ctx.logger.info(f"Sent CallToolResponse to {sender} for tool={msg.tool}")
            except Exception as e:
                error_msg = f"Error: Failed to call tool {msg.tool}"
                ctx.logger.error(f"{error_msg}: {str(e)}")
                await ctx.send(
                    sender,
                    CallToolResponse(
                        id=msg.id,  # Include the id from the request
                        result=None,
                        error={"message": error_msg}
                    )
                )
        
        # Register the handler with the appropriate protocol(s)
        if self.dual_mode and self.asi1_mode:
            # In dual mode, register with both protocol sets
            @self.bridge_mcp_protocol.on_message(model=CallTool)
            async def handle_bridge_call_tool(ctx: Context, sender: str, msg: CallTool):
                await handle_call_tool_impl(ctx, sender, msg)
                
            @self.asi1_mcp_protocol.on_message(model=CallTool)
            async def handle_asi1_call_tool(ctx: Context, sender: str, msg: CallTool):
                await handle_call_tool_impl(ctx, sender, msg)
        else:
            # In single mode, register with the active protocol
            @self.mcp_protocol.on_message(model=CallTool)
            async def handle_call_tool(ctx: Context, sender: str, msg: CallTool):
                await handle_call_tool_impl(ctx, sender, msg)
    
    def _setup_chat_protocol_handlers(self):
        """Set up handlers for chat protocol messages."""
        
        async def handle_chat_message_impl(ctx: Context, sender: str, msg: ChatMessage, protocol_type=None):
            """Implementation of chat message handler."""
            # Send acknowledgement for the message
            ack = ChatAcknowledgement(
                timestamp=datetime.now(timezone.utc),
                acknowledged_msg_id=msg.msg_id
            )
            await ctx.send(sender, ack)
            
            for item in msg.content:
                if isinstance(item, StartSessionContent):
                    ctx.logger.info(f"Got a start session message from {sender}")
                elif isinstance(item, TextContent):
                    ctx.logger.info(f"Got a message from {sender}: {item.text}")
                    
                    # Process the message based on the mode and protocol type
                    if protocol_type == "asi1" or (self.asi1_mode and not self.dual_mode):
                        await self._process_asi1_message(ctx, sender, item.text)
                    else:
                        await self._process_bridge_message(ctx, sender, item.text)
                else:
                    ctx.logger.info(f"Got unexpected content type from {sender}")
        
        async def handle_ack_impl(ctx: Context, sender: str, msg: ChatAcknowledgement):
            """Implementation of chat acknowledgement handler."""
            ctx.logger.info(f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}")
            if msg.metadata:
                ctx.logger.info(f"Metadata: {msg.metadata}")
        
        # Register the handlers with the appropriate protocol(s)
        if self.dual_mode and self.asi1_mode:
            # In dual mode, register with both protocol sets
            @self.bridge_chat_protocol.on_message(model=ChatMessage)
            async def handle_bridge_chat_message(ctx: Context, sender: str, msg: ChatMessage):
                await handle_chat_message_impl(ctx, sender, msg, protocol_type="bridge")
                
            @self.asi1_chat_protocol.on_message(model=ChatMessage)
            async def handle_asi1_chat_message(ctx: Context, sender: str, msg: ChatMessage):
                await handle_chat_message_impl(ctx, sender, msg, protocol_type="asi1")
                
            @self.bridge_chat_protocol.on_message(model=ChatAcknowledgement)
            async def handle_bridge_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
                await handle_ack_impl(ctx, sender, msg)
                
            @self.asi1_chat_protocol.on_message(model=ChatAcknowledgement)
            async def handle_asi1_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
                await handle_ack_impl(ctx, sender, msg)
        else:
            # In single mode, register with the active protocol
            @self.chat_protocol.on_message(model=ChatMessage)
            async def handle_chat_message(ctx: Context, sender: str, msg: ChatMessage):
                await handle_chat_message_impl(ctx, sender, msg)
            
            @self.chat_protocol.on_message(model=ChatAcknowledgement)
            async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
                await handle_ack_impl(ctx, sender, msg)
    
    async def _process_bridge_message(self, ctx: Context, sender: str, text: str):
        """Process a message in bridge mode (for Claude Desktop integration)."""
        try:
            # Simple approach: Try to find a tool that matches the request
            tools = await self.mcp_server.list_tools()
            
            # Very basic tool selection based on text matching
            # In a real implementation, this would use an LLM or more sophisticated matching
            user_text = text.lower()
            selected_tool = None
            tool_args = {}
            
            for tool in tools:
                # Handle both object-style and dict-style tools
                tool_name = tool.name if hasattr(tool, 'name') else tool.get('name', '')
                
                if tool_name.lower() in user_text:
                    selected_tool = tool_name
                    
                    # Extract arguments based on the tool's input schema
                    tool_schema = tool.inputSchema if hasattr(tool, 'inputSchema') else tool.get('inputSchema', {})
                    if tool_schema and "properties" in tool_schema:
                        for param_name, param_info in tool_schema["properties"].items():
                            # Very basic parameter extraction
                            # In a real implementation, this would use an LLM or more sophisticated extraction
                            param_desc = param_info.get("description", "").lower()
                            if param_desc and param_desc in user_text:
                                # Find the value after the parameter description
                                parts = user_text.split(param_desc)
                                if len(parts) > 1:
                                    value = parts[1].strip().split()[0].strip('.,!?')
                                    tool_args[param_name] = value
                            elif param_name.lower() in user_text:
                                # Find the value after the parameter name
                                parts = user_text.split(param_name.lower())
                                if len(parts) > 1:
                                    value = parts[1].strip().split()[0].strip('.,!?')
                                    tool_args[param_name] = value
                    
                    break
            
            # Call the selected tool or respond that no tool was found
            if selected_tool:
                try:
                    ctx.logger.info(f"Calling tool '{selected_tool}' with arguments: {tool_args}")
                    output = await self.mcp_server.call_tool(selected_tool, tool_args)
                    
                    # Format the result as a response
                    if isinstance(output, dict):
                        response_text = json.dumps(output, indent=2)
                    elif isinstance(output, list):
                        response_text = "\n".join(str(r) for r in output)
                    else:
                        response_text = str(output)
                        
                    ctx.logger.info(f"Tool response: {response_text}")
                except Exception as e:
                    ctx.logger.error(f"Error calling tool {selected_tool}: {str(e)}")
                    response_text = f"I encountered an issue while using the {selected_tool} tool."
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
            ctx.logger.error(f"Error processing chat message: {str(e)}")
            await ctx.send(
                sender,
                ChatMessage(
                    timestamp=datetime.now(timezone.utc),
                    msg_id=uuid4(),
                    content=[TextContent(type="text", text=f"I encountered an error: {str(e)}")]
                )
            )
    
    async def _process_asi1_message(self, ctx: Context, sender: str, text: str):
        """Process a message in ASI1 mode (direct ASI1 API integration)."""
        try:
            # Get message history from storage
            messages_key = f"messages-{str(ctx.session)}"
            try:
                messages_serialized = ctx.storage.get(messages_key)
                messages = json.loads(messages_serialized) if messages_serialized else []
            except Exception as e:
                ctx.logger.error(f"Error loading message history: {str(e)}")
                messages = []

            # Add system prompt if not present
            system_prompt = {
                "role": "system",
                "content": (
                     "You are a helpful and intelligent assistant that can only respond"
                    " by using the tools provided to you. "
                    "For every user request, choose the most relevant tool available"
                    " to generate your response. "
                    "If no tool is suitable for answering the question, kindly reply"
                     " with something like "
                    "'I'm sorry, I can't help with that right now.' or "
                    "'That's outside what I can assist with.' "
                    "Always keep your tone polite, concise, and friendly."
                )
            }

            messages = [m for m in messages if m.get("role") != "system"]
            messages.insert(0, system_prompt)

            # Add user message
            user_message = {"role": "user", "content": text.strip()}
            messages.append(user_message)

            ctx.logger.info(f"Sending message to ASI1: {json.dumps(user_message, indent=2)}")

            # Get tools from MCP server
            try:
                tools = await self.mcp_server.list_tools()
                available_tools = []
                
                for tool in tools:
                    # Handle both object-style and dict-style tools
                    tool_name = tool.name if hasattr(tool, 'name') else tool.get('name', '')
                    tool_desc = tool.description if hasattr(tool, 'description') else tool.get('description', '')
                    tool_schema = tool.inputSchema if hasattr(tool, 'inputSchema') else tool.get('inputSchema', {})
                    
                    ctx.logger.info(f"Tool Name: {tool_name}")
                    ctx.logger.info(f"Description: {tool_desc}")
                    ctx.logger.info(f"Parameters: {json.dumps(tool_schema, indent=2)}")
                    
                    available_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": tool_desc,
                            "parameters": tool_schema
                        }
                    })
            except Exception as e:
                ctx.logger.error(f"Error: Failed to retrieve tools from MCP Server: {str(e)}")
                available_tools = []

            ctx.logger.info(f"Available tools for ASI1: {json.dumps(available_tools, indent=2)}")

            # Prepare payload for ASI1
            payload = {
                "model": self.model,
                "messages": messages,
                "tools": available_tools,
                "tool_choice": "auto",  # Use auto to let the model decide whether to use a tool
                "temperature": 0.7,
                "max_tokens": 1024
            }

            headers = {
                "Authorization": f"Bearer {self.asi1_api_key}",
                "Content-Type": "application/json"
            }

            # Make API call to ASI1
            try:
                # Log the request details (but mask the auth token for security)
                masked_auth = headers["Authorization"][:15] + "..." if len(headers["Authorization"]) > 15 else "***"
                debug_headers = {**headers, "Authorization": masked_auth}
                ctx.logger.info(f"Making API call to: {self.asi1_base_url}/chat/completions")
                ctx.logger.info(f"Headers: {json.dumps(debug_headers, indent=2)}")
                ctx.logger.info(f"Model being used: {payload['model']}")
                
                # Make the actual API call
                response = requests.post(f"{self.asi1_base_url}/chat/completions", headers=headers, json=payload)
                
                # Log response status and details
                ctx.logger.info(f"ASI1 API response status: {response.status_code}")
                
                # Parse the response
                response_json = response.json()
            except Exception as e:
                ctx.logger.error(f"Error calling ASI1 API: {str(e)}")
                error_msg = "I'm having trouble connecting to the AI service. Please try again in a moment."
                await ctx.send(sender, ChatMessage(
                    timestamp=datetime.now(timezone.utc),
                    msg_id=uuid4(),
                    content=[TextContent(type="text", text=error_msg)]
                ))
                return

            ctx.logger.info(f"Raw LLM response: {json.dumps(response_json, indent=2)}")

            if response_json.get("choices"):
                assistant_message = response_json["choices"][0]["message"]
                assistant_msg = {"role": "assistant", "content": assistant_message.get("content", "")}

                if assistant_message.get("tool_calls"):
                    assistant_msg["tool_calls"] = assistant_message["tool_calls"]
                    messages.append(assistant_msg)

                    # Process tool calls
                    for tool_call in assistant_message["tool_calls"]:
                        selected_tool = tool_call["function"]["name"]
                        try:
                            tool_args = json.loads(tool_call["function"]["arguments"])
                        except Exception as e:
                            ctx.logger.error(f"Error parsing tool arguments: {str(e)}")
                            error_msg = f"There was an issue processing the tool arguments for {selected_tool}"
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": error_msg
                            })
                            continue

                        ctx.logger.info(f"Calling tool '{selected_tool}' with arguments: {json.dumps(tool_args, indent=2)}")

                        try:
                            tool_results = await self.mcp_server.call_tool(selected_tool, tool_args)
                            response_text = "\n".join(str(r) for r in tool_results) if isinstance(tool_results, list) else str(tool_results)
                            ctx.logger.info(f"Tool '{selected_tool}' response: {response_text}")
                        except Exception as e:
                            response_text = f"I encountered an issue while using the {selected_tool} tool."
                            ctx.logger.error(f"Error calling tool {selected_tool}: {str(e)}")

                        ctx.logger.info(f"Tool '{selected_tool}' response: {response_text}")

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": response_text
                        })

                    # Get final response after tool calls
                    try:
                        follow_up_payload = {
                            "model": self.model,
                            "messages": messages,
                            "temperature": 0.7,
                            "max_tokens": 1024
                        }

                        follow_up_response = requests.post(f"{self.asi1_base_url}/chat/completions", headers=headers, json=follow_up_payload)
                        follow_up_json = follow_up_response.json()
                        final_response = follow_up_json.get("choices", [{}])[0].get("message", {}).get(
                            "content",
                            "I've processed your request and gathered the information. Let me know if you need anything else!"
                        )
                    except Exception as e:
                        ctx.logger.error(f"Error getting final response from ASI1: {str(e)}")
                        final_response = "I'm having trouble connecting to the AI service. Please try again in a moment."
                else:
                    messages.append(assistant_msg)
                    final_response = assistant_message.get(
                        "content",
                        "I'm having trouble connecting to the AI service. Please try again in a moment!"
                    )
            else:
                ctx.logger.error("❌ Invalid response format from ASI1: missing 'choices'")
                final_response = "I'm experiencing some technical difficulties. Please try again in a moment."

            # Save updated message history
            try:
                ctx.storage.set(messages_key, json.dumps(messages))
            except Exception as e:
                ctx.logger.error(f"Error saving message history: {str(e)}")

            # Send final response to user
            await ctx.send(sender, ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=uuid4(),
                content=[TextContent(type="text", text=final_response)]
            ))

        except Exception as e:
            error_msg = "I'm experiencing some technical difficulties. Please try again in a moment."
            ctx.logger.error(f"Unexpected error in ASI1 chat handler: {str(e)}")
            await ctx.send(sender, ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=uuid4(),
                content=[TextContent(type="text", text=error_msg)]
            ))
    
    def register_with_agent(self, agent: Agent):
        """Register the adapter's protocols with the agent."""
        # Create a dictionary to track registered protocols to avoid duplicates
        registered_protocols = {}
        
        def safe_include(protocol, protocol_name=None):
            """Safely include a protocol, avoiding duplicates"""
            name = protocol_name or protocol.name
            if name in registered_protocols:
                logger.debug(f"Protocol {name} already registered with this agent")
                return False
                
            try:
                agent.include(protocol)
                registered_protocols[name] = True
                return True
            except RuntimeError as e:
                if "duplicate model" in str(e).lower():
                    logger.debug(f"Protocol {name} already registered with agent {agent.name}")
                    registered_protocols[name] = True
                    return False
                else:
                    raise
        
        try:
            # Register the protocols based on the mode
            if self.dual_mode:
                # In dual mode, register both sets of protocols
                asi1_mcp_registered = safe_include(self.asi1_mcp_protocol, "MCPProtocol")
                asi1_chat_registered = safe_include(self.asi1_chat_protocol, "AgentChatProtocol")
                
                # Only try to register bridge protocols if they're different from ASI1 protocols
                if not asi1_mcp_registered:
                    safe_include(self.bridge_mcp_protocol, "MCPProtocol")
                if not asi1_chat_registered:
                    safe_include(self.bridge_chat_protocol, "AgentChatProtocol")
                    
                logger.info("Registered protocols with the agent for dual mode operation")
            else:
                # In single mode, register the appropriate protocols
                safe_include(self.mcp_protocol)
                safe_include(self.chat_protocol)
                logger.info("Registered protocols with the agent")
                
        except Exception as e:
            logger.error(f"Error registering protocols: {str(e)}")
            raise
            
        logger.info(f"Registered FastMCP adapter with agent {agent.name}")

    def run(self, agent: Agent, transport: Optional[str] = None):
        """Run the adapter with the given agent.
        
        Args:
            agent: The uAgent to run with
            transport: Optional transport mode (e.g., 'stdio' for ASI1 integration)
        """
        try:
            # Start the agent in a background thread
            # We don't need to register protocols here as that should be done separately via register_with_agent
            agent_thread = threading.Thread(target=agent.run, daemon=True)
            agent_thread.start()
            logger.info("Started agent in a background thread")
            
            # Start the MCP server if it has a run method
            if hasattr(self.mcp_server, 'run') and callable(self.mcp_server.run):
                logger.info(f"Starting MCP server with transport: {transport or 'stdio'}")
                self.mcp_server.run(transport=transport or "stdio")
            else:
                logger.warning("MCP server does not have a run method")
                # Keep the main thread alive for ASI1 integration
                logger.info("Keeping main thread alive for dual mode operation")
                while True:
                    time.sleep(1)
        except Exception as e:
            logger.error(f"Error running adapter: {str(e)}")
            raise

# For backward compatibility, provide MCPServerAdapter as an alias for FastMCPAdapter in ASI1 mode
class MCPServerAdapter(FastMCPAdapter):
    """Adapter for integrating uAgents with Model Control Protocol (MCP) servers.
    
    This is an alias for FastMCPAdapter in ASI1 mode for backward compatibility.
    """
    
    def __init__(
        self,
        mcp_server: Any,
        asi1_api_key: str,
        model: str,
        asi1_base_url: str = ASI1_BASE_URL,
        dual_mode: bool = False,
    ):
        """
        Initialize the MCP adapter.

        Args:
            mcp_server: The MCP server instance
            asi1_api_key: API key for ASI1 service
            model: Model name to use for ASI1 service
            asi1_base_url: Base URL for ASI1 API (default: "https://api.asi1.ai/v1")
            dual_mode: Whether to support both ASI1 and bridge modes simultaneously
        """
        super().__init__(
            mcp_server=mcp_server,
            name="mcp_server_adapter",
            asi1_api_key=asi1_api_key,
            model=model,
            asi1_base_url=asi1_base_url,
            dual_mode=dual_mode,
        )
