from kubectl_mcp_tools import kubectl_mcp
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from fastmcp.server.http import create_sse_app
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Starlette(
    routes=[
        Mount('/kubectl_mcp_tools', app=create_sse_app(kubectl_mcp, "/messages/", "/sse")),
    ]
)

if __name__ == "__main__":
    logger.info("Starting SREArena MCP Server")
    uvicorn.run(app, host="127.0.0.1", port=8000)
