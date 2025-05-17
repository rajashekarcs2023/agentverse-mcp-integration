#!/usr/bin/env python3
"""FastMCP weather agent using the custom uagent_mcp library."""

import os
import sys
import logging
from dotenv import load_dotenv
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
    # Load environment variables from .env file
    load_dotenv()
    
    # Create the agent
    agent = Agent(
        name="weather_agent",
        port=8003,
        # Use either endpoint or mailbox, not both
        # endpoint=["http://127.0.0.1:8003/submit"],
        mailbox=True
    )
    
    # Get API key from environment variable for security
    asi1_api_key = os.environ.get("ASI1_API_KEY", "")
    
    # Print debug information about the API key (masking most of it for security)
    if asi1_api_key:
        masked_key = asi1_api_key[:4] + "*" * (len(asi1_api_key) - 8) + asi1_api_key[-4:] if len(asi1_api_key) > 8 else "****"
        logger.info(f"ASI1 API key loaded: {masked_key}")
    else:
        logger.warning("No ASI1 API key found in environment variables")
        logger.info("Available environment variables: " + ", ".join(list(os.environ.keys())[:10]) + "...")
    
    # Create a FastMCPAdapter with dual mode (both ASI1 and bridge) enabled by default
    # Note: dual_mode is now True by default in the FastMCPAdapter
    adapter = FastMCPAdapter(
        mcp_server=mcp,
        name="weather_adapter",
        asi1_api_key=asi1_api_key,
        model="asi1-mini"  # Using ASI1 model name
    )
    
    if asi1_api_key:
        logger.info("Using FastMCPAdapter in dual mode with ASI1 integration")
    else:
        logger.info("Using FastMCPAdapter in bridge mode only (no ASI1 API key provided)")
        logger.warning("For dual mode functionality, please set ASI1_API_KEY in your .env file")
    
    # Register the adapter with the agent
    adapter.register_with_agent(agent)
    
    # Print the agent address for reference
    logger.info(f"Starting FastMCP weather agent with address: {agent.address}")
    
    # Run the agent
    adapter.run(agent)

if __name__ == "__main__":
    main()
