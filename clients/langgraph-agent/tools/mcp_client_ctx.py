"""Creates all MCP client contexts for tools to inherit and use"""

import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack
from typing import AsyncContextManager, Optional

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()  # load environment variables from .env
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MCPClientCtxManager:
    def __init__(self, server_paths: dict[str, str]):
        # Initialize session and client objects
        self.sessions: dict[str, ClientSession] = dict()
        self.exit_stack = AsyncExitStack()
        self.server_paths = server_paths

    async def connect_to_servers(self):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        # TODO: how to connect to remotely hosted mcp server?
        for server_name, server_path in self.server_paths.items():
            is_python = server_path.endswith(".py")
            is_js = server_path.endswith(".js")
            if not (is_python or is_js):
                raise ValueError("Server script must be a .py or .js file")

            command = (
                sys.executable  # Uses the current Python interpreter from the activated venv
                if is_python
                else "node"
            )
            server_params = StdioServerParameters(
                command=command, args=[server_path], env=None
            )

            logging.info(f"Starting server: {server_name} with params: {server_params}")

            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            stdio, write = stdio_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )

            await session.initialize()
            logger.info(f"Connected to server: {server_name}, adding to session dict")
            self.sessions[server_name] = session

            logger.info(f"Listing tools for server: {server_name}")
            response = await session.list_tools()
            tools = response.tools
            logger.info(
                "Connected to server with tools: %s", [tool.name for tool in tools]
            )

    def ctx_selector(self, server_name: str):
        """Selects the right session to use for the tool"""
        return self.sessions[server_name]
