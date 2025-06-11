import os
from unittest.mock import MagicMock, patch

import pytest
from langchain.agents.chat.prompt import HUMAN_MESSAGE
from langchain_core.messages import HumanMessage, ToolMessage

from clients.langgraph_agent.state import State
from clients.langgraph_agent.tools.text_editing.file_manip import create, edit, goto_line, insert, open_file


@pytest.fixture
def mock_tool_call_id():
    return "mock_tool_call_id"


@pytest.fixture
def temp_file(tmp_path):
    file_path = tmp_path / "test_file.txt"
    with open(file_path, "w") as f:
        f.write("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
    return str(file_path)


@pytest.fixture
def open_mock_state(temp_file):
    return State(
        messages=[
            HumanMessage(content="hello"),
            ToolMessage(
                tool_call_id="abc",
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": "call_3vHND9gcYpfAFIHFLO35zX2w",
                            "function": {
                                "arguments": f'"path": {temp_file},"line_number":"1"',
                                "name": "open_file",
                            },
                            "type": "function",
                        }
                    ],
                    "refusal": None,
                },
                response_metadata={
                    "token_usage": {
                        "completion_tokens": 36,
                        "prompt_tokens": 653,
                        "total_tokens": 689,
                        "completion_tokens_details": {
                            "accepted_prediction_tokens": 0,
                            "audio_tokens": 0,
                            "reasoning_tokens": 0,
                            "rejected_prediction_tokens": 0,
                        },
                        "prompt_tokens_details": {"audio_tokens": 0, "cached_tokens": 0},
                    },
                    "model_name": "gpt-4o-2024-08-06",
                    "system_fingerprint": "fp_07871e2ad8",
                    "id": "chatcmpl-BhMroSwI7MlaCBHBmELAyM1nlT7H1",
                    "service_tier": "default",
                    "finish_reason": "tool_calls",
                    "logprobs": None,
                },
                id="run--80b17920-4e5e-427a-b953-c283a0ab98d7-0",
                tool_calls=[
                    {
                        "name": "open_file",
                        "args": {
                            "path": f"{temp_file}",
                            "line_number": "1",
                        },
                        "id": "call_3vHND9gcYpfAFIHFLO35zX2w",
                        "type": "tool_call",
                    }
                ],
                usage_metadata={
                    "input_tokens": 653,
                    "output_tokens": 36,
                    "total_tokens": 689,
                    "input_token_details": {"audio": 0, "cache_read": 0},
                    "output_token_details": {"audio": 0, "reasoning": 0},
                },
            ),
        ],
        curr_file="mock_file.py",
        curr_line=42,
    )


class TestOpenFile:
    @patch("os.path.exists")
    @patch("os.path.isfile")
    def test_open_file_success(self, mock_isfile, mock_exists, open_mock_state, temp_file, mock_tool_call_id):
        mock_exists.return_value = True
        mock_isfile.return_value = True

        tool_args = {
            "args": {"state": open_mock_state, "path": temp_file},
            "name": "open",
            "type": "tool_call",
            "id": mock_tool_call_id,
        }

        result = open_file.invoke(tool_args)

        assert "Line 1" in result
        assert "Successfully opened" in result.messages[-1]["content"]

    @patch("os.path.exists")
    def test_open_file_not_exists(self, mock_exists, mock_state):
        mock_exists.return_value = False

        result = open_file.invoke(mock_state, path="/nonexistent/file.txt")

        assert "does not exist" in result.messages[-1]["content"]

    @patch("os.path.exists")
    @patch("os.path.isfile")
    def test_open_file_not_a_file(self, mock_isfile, mock_exists, mock_state):
        mock_exists.return_value = True
        mock_isfile.return_value = False

        result = open_file.invoke(mock_state, path="/some/directory")

        assert "is not a file" in mock_state["messages"][-1]["content"]

    def test_open_file_with_line_number(self, mock_state, temp_file):
        result = open_file.invoke(mock_state, path=temp_file, line_number=3)

        assert mock_state["curr_file"] == temp_file
        assert mock_state["curr_line"] == 3
        assert "Successfully opened" in result.messages[-1]["content"]


# class TestGotoLine:
#     def test_goto_line_success(self, mock_state, temp_file):
#         state_with_file = mock_state
#         state_with_file.curr_file = temp_file
#
#         result = goto_line(state_with_file, line_number=3)
#
#         assert result.curr_line == 3
#         assert "Successfully moved to line 3" in result.messages[-1]["content"]
#
#     def test_goto_line_no_current_file(self, mock_state):
#         state_no_file = mock_state
#         state_no_file.curr_file = None
#
#         result = goto_line(state_no_file, line_number=3)
#
#         assert "No file is currently open" in result.messages[-1]["content"]
#
#     def test_goto_line_invalid_line_number(self, mock_state, temp_file):
#         state_with_file = mock_state
#         state_with_file.curr_file = temp_file
#
#         result = goto_line(state_with_file, line_number=100)
#
#         assert "Line number 100 is out of range" in result.messages[-1]["content"]
#
#
# class TestCreate:
#     @patch('os.path.exists')
#     def test_create_file_success(self, mock_exists, mock_state, tmp_path):
#         new_file_path = str(tmp_path / "new_file.txt")
#         mock_exists.return_value = False
#
#         result = create(mock_state, path=new_file_path, content="New file content")
#
#         assert os.path.exists(new_file_path)
#         assert result.curr_file == new_file_path
#         assert "Successfully created" in result.messages[-1]["content"]
#
#         with open(new_file_path, 'r') as f:
#             content = f.read()
#         assert content == "New file content"
#
#     @patch('os.path.exists')
#     def test_create_file_already_exists(self, mock_exists, mock_state):
#         mock_exists.return_value = True
#
#         result = create(mock_state, path="/existing/file.txt", content="Content")
#
#         assert "already exists" in result.messages[-1]["content"]
#
#
# class TestEdit:
#     def test_edit_replace_success(self, mock_state, temp_file):
#         state_with_file = mock_state
#         state_with_file.curr_file = temp_file
#
#         result = edit(
#             state_with_file,
#             find="Line 2",
#             replace="Modified Line 2"
#         )
#
#         assert "Successfully edited" in result.messages[-1]["content"]
#
#         with open(temp_file, 'r') as f:
#             content = f.read()
#         assert "Modified Line 2" in content
#         assert "Line 2" not in content
#
#     def test_edit_no_current_file(self, mock_state):
#         state_no_file = mock_state
#         state_no_file.curr_file = None
#
#         result = edit(
#             state_no_file,
#             find="something",
#             replace="something else"
#         )
#
#         assert "No file is currently open" in result.messages[-1]["content"]
#
#     def test_edit_pattern_not_found(self, mock_state, temp_file):
#         state_with_file = mock_state
#         state_with_file.curr_file = temp_file
#
#         result = edit(
#             state_with_file,
#             find="Nonexistent Pattern",
#             replace="Something"
#         )
#
#         assert "not found" in result.messages[-1]["content"]
#
#     def test_edit_with_window(self, mock_state, temp_file):
#         state_with_file = mock_state
#         state_with_file.curr_file = temp_file
#
#         result = edit(
#             state_with_file,
#             find="Line",
#             replace="Modified",
#             window="Line 3"
#         )
#
#         assert "Successfully edited" in result.messages[-1]["content"]
#
#         with open(temp_file, 'r') as f:
#             content = f.read()
#         assert "Modified 3" in content
#         assert "Line 3" not in content
#
#
# class TestInsert:
#     def test_insert_at_line_success(self, mock_state, temp_file):
#         state_with_file = mock_state
#         state_with_file.curr_file = temp_file
#
#         result = insert(
#             state_with_file,
#             content="Inserted Line",
#             line_number=3
#         )
#
#         assert "Successfully inserted" in result.messages[-1]["content"]
#
#         with open(temp_file, 'r') as f:
#             content = f.read()
#
#         lines = content.strip().split('\n')
#         assert lines[2] == "Inserted Line"
#         assert lines[3] == "Line 3"
#
#     def test_insert_no_current_file(self, mock_state):
#         state_no_file = mock_state
#         state_no_file.curr_file = None
#
#         result = insert(
#             state_no_file,
#             content="Inserted Line",
#             line_number=3
#         )
#
#         assert "No file is currently open" in result.messages[-1]["content"]
#
#     def test_insert_invalid_line_number(self, mock_state, temp_file):
#         state_with_file = mock_state
#         state_with_file.curr_file = temp_file
#
#         result = insert(
#             state_with_file,
#             content="Inserted Line",
#             line_number=100
#         )
#
#         assert "Line number 100 is out of range" in result.messages[-1]["content"]
#
#     def test_insert_at_current_line(self, mock_state, temp_file):
#         state_with_file = mock_state
#         state_with_file.curr_file = temp_file
#         state_with_file.curr_line = 2
#
#         result = insert(
#             state_with_file,
#             content="Inserted at Current Line"
#         )
#
#         assert "Successfully inserted" in result.messages[-1]["content"]
#
#         with open(temp_file, 'r') as f:
#             content = f.read()
#
#         lines = content.strip().split('\n')
#         assert lines[1] == "Inserted at Current Line"
#         assert lines[2] == "Line 2"
