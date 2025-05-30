import asyncio
import json
import logging
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.constants import END
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from llm_backend.init_backend import get_llm_backend_for_tools
from tools.jaeger_tools import *
from tools.mcp_client_ctx import MCPClientCtxManager
from typing_extensions import TypedDict

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]


llm = get_llm_backend_for_tools()


def agent(state: State):
    return {"messages": [llm.inference(messages=state["messages"])]}


def route_tools(state: State):
    """
    Use in the conditional_edge to route to the ToolNode if the last message
    has tool calls. Otherwise, route to the end.
    """
    if isinstance(state, list):
        ai_message = state[-1]
    elif messages := state.get("messages", []):
        ai_message = messages[-1]
    else:
        raise ValueError(f"No messages found in input state to tool_edge: {state}")
    if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        return "observability_tool_node"
    return END


graph_builder = StateGraph(State)
graph_builder.add_node("agent", agent)

tools = [
    get_traces,
    get_services,
    get_operations,
]

mcp_ctx_manager = MCPClientCtxManager(
    {"observability": "../../mcp_server/observability_server.py"}
)
try:
    asyncio.run(mcp_ctx_manager.connect_to_servers())
except Exception as e:
    logger.error(f"Error connecting to MCP servers: {e}")
    exit(1)


class BasicToolNode:
    """A node that runs the tools requested in the last AIMessage."""

    def __init__(self, node_tools: list[BaseTool]) -> None:
        self.tools_by_name = {t.name: t for t in node_tools}

    def __call__(self, inputs: dict):
        if messages := inputs.get("messages", []):
            message = messages[-1]
        else:
            raise ValueError("No message found in input")
        outputs = []
        for tool_call in message.tool_calls:
            # choosing the right ctx by tools called
            # assuming we have different mcp servers for different tools
            match tool_call["name"]:
                case "get_traces" | "get_services" | "get_operations":
                    session = mcp_ctx_manager.ctx_selector("observability")
                    # TODO: this should pass the correct ctx to the langchain tool
                    tool_result = self.tools_by_name[tool_call["name"]].invoke(
                        [session] + tool_call["args"]
                    )
                case _:
                    tool_result = {"error": "Tool not found"}
                    logger.warning(f"Tool {tool_call['name']} not found")
            outputs.append(
                ToolMessage(
                    content=json.dumps(tool_result),
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": outputs}


observability_tool_node = BasicToolNode(tools)
graph_builder.add_node("observability_tool_node", observability_tool_node)
graph_builder.add_edge(START, "agent")
# agent -> ob tool -> agent (loop)
# agent -> end
graph_builder.add_conditional_edges(
    "agent",
    route_tools,
    # The following dictionary lets you tell the graph to interpret the condition's outputs as a specific node
    # It defaults to the identity function, but if you
    # want to use a node named something else apart from "tools",
    # You can update the value of the dictionary to something else
    # e.g., "tools": "my_tools"
    {"observability_tool_node": "observability_tool_node", END: END},
)
graph_builder.add_edge("observability_tool_node", "agent")
graph = graph_builder.compile()


def stream_graph_updates(user_input: str):
    for event in graph.stream({"messages": [{"role": "user", "content": user_input}]}):
        for value in event.values():
            logger.info("Assistant:", value["messages"][-1].content)


while True:
    try:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        stream_graph_updates(user_input)
    except:
        # fallback if input() is not available
        break
