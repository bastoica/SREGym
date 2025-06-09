import asyncio
import logging
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import InjectedState

from clients.langgraph_agent.state import State

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class FileToolNode:
    """A node that runs the file tools requested in the last AIMessage."""

    def __init__(self, node_tools: list[BaseTool]) -> None:
        self.tools_by_name = {t.name: t for t in node_tools}

    def __call__(self, inputs: Annotated[State, InjectedState]):
        logger.info(f"FileToolNode: {inputs}")
        if messages := inputs.get("messages", []):
            message = messages[-1]
        else:
            raise ValueError("No message found in input")

        logger.info(f"FileToolNode: {message}")
        outputs = []
        for tool_call in message.tool_calls:
            logger.info(f"invoking tool: {tool_call["name"]}, tool_call: {tool_call["args"]}")
            tool_result = self.tools_by_name[tool_call["name"]].invoke(input, **tool_call["args"])
            logger.info(f"tool_result: {tool_result}")
            tool_result_content = []
            for text_content in tool_result.content:
                tool_result_content.append(text_content.text)
            outputs.append(
                ToolMessage(
                    content=tool_result,
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": outputs}


class BasicToolNode:
    """A node that runs the file tools requested in the last AIMessage."""

    def __init__(self, node_tools: list[BaseTool], is_async: bool) -> None:
        self.tools_by_name = {t.name: t for t in node_tools}
        self.is_async = is_async

    def __call__(self, inputs: dict):
        if messages := inputs.get("messages", []):
            message = messages[-1]
        else:
            raise ValueError("No message found in input")
        logger.info(f"BasicToolNode: {message}")
        outputs = []
        for tool_call in message.tool_calls:
            logger.info(f"invoking tool: {tool_call["name"]}, tool_call: {tool_call}")
            if self.is_async:
                tool_result = asyncio.run(self.tools_by_name[tool_call["name"]].ainvoke(tool_call["args"]))
            else:
                tool_result = self.tools_by_name[tool_call["name"]].invoke(tool_call["args"])
            logger.info(f"tool_result: {tool_result}")
            tool_result_content = []
            for text_content in tool_result.content:
                tool_result_content.append(text_content.text)
            outputs.append(
                ToolMessage(
                    content=tool_result,
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": outputs}
