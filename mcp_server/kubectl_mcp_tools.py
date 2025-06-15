import logging
import os

from fastmcp import FastMCP, Context
from yarl import URL
from cachetools import TTLCache
from kubectl_server_helper.kubectl_cmd_runner import KubectlCmdRunner
from kubectl_server_helper.rollback_tool import RollbackTool
from kubectl_server_helper.config import KubectlToolCfg
from mcp_server.kubectl_server_helper.action_stack import ActionStack

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# max size of the session cache
session_cache_size = 10000
# Time to live after last time access (in seconds)
ttl = 10 * 60

sessionCache = TTLCache(maxsize=session_cache_size,
                        ttl=ttl)
kubectl_mcp = FastMCP("Kubectl MCP Server")


class KubectlTool:
    def __init__(self, session_id: str):
        self.ssid = session_id

        self.config = KubectlToolCfg()
        self.config.output_dir = os.path.join(
            self.config.output_dir,
            self.ssid
        )

        self.action_stack = None
        if self.config.use_rollback_stack:
            self.action_stack = ActionStack()

        self.cmd_runner = KubectlCmdRunner(self.config, self.action_stack)
        self.rollback_tool = RollbackTool(self.config, self.action_stack)


def extract_session_id(ctx: Context):
    """
    Use this function to get the session id of the request
    """
    str_url = str(ctx.request_context.request.url)
    url = URL(str_url)
    ssid = url.query.get("session_id")
    return ssid


def get_tools(session_id: str) -> KubectlTool:
    """
    Get the tools related with session_id. If no
    tools, create a new one for this session.
    """
    if session_id in sessionCache:
        logger.info(f"session {session_id} is accessing its kubectl tool.")
        return sessionCache[session_id]

    logger.info(f"Creating a new kubectl tool for session {session_id}.\n "
                f"Current cache size is {len(sessionCache)}")
    tool = KubectlTool(session_id)
    sessionCache[session_id] = tool
    return tool


@kubectl_mcp.tool()
def exec_kubectl_cmd_safely(cmd: str, ctx: Context) -> str:
    """
    Use this function to execute kubectl commands.
    Args:
        cmd: The command you want to execute in a CLI to
        manage a k8s cluster. It should start with "kubectl".
        ctx: If you are an agent, you can safely ignore this
        argument.
    Returns:
        The result of trying to execute cmd.
    """
    ssid = extract_session_id(ctx)
    kubctl_tool = get_tools(ssid)
    return kubctl_tool.cmd_runner.exec_kubectl_cmd_safely(cmd)


@kubectl_mcp.tool()
def rollback_command(ctx: Context) -> str:
    """
    Use this function to roll back the last kubectl command
    you successfully executed with the "exec_kubectl_cmd_safely" tool.
    Args:
        ctx: If you are an agent, you can safely ignore this
        argument.
    Returns:
        The result of trying to roll back the last kubectl command.
    """
    ssid = extract_session_id(ctx)
    kubctl_tool = get_tools(ssid)
    return kubctl_tool.rollback_tool.rollback()
