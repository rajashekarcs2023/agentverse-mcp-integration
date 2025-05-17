#!/usr/bin/env python3
"""FastMCP weather agent using the custom uagent_mcp library."""

import os
import sys
import logging
from uagents import Agent

# Add the parent directory to the path so we can import our custom library
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our custom library
from uagent_mcp import FastMCPAdapter
from fastmcp_server import mcp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("fastmcp_agent")

def main():
    """Main function to run the FastMCP weather agent."""
    # Create the agent
    agent = Agent(
        name="weather_agent",
        port=8003,
        # Use either endpoint or mailbox, not both
        # endpoint=["http://127.0.0.1:8003/submit"],
        mailbox=True
    )
    
    # Create the adapter
    adapter = FastMCPAdapter(mcp_server=mcp, name="weather_adapter")
    
    # Register the adapter with the agent
    adapter.register_with_agent(agent)
    
    # Print the agent address for reference
    logger.info(f"Starting FastMCP weather agent with address: {agent.address}")
    
    # Run the agent
    adapter.run(agent)

if __name__ == "__main__":
    main()
