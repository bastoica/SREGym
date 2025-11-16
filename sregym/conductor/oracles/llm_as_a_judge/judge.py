"""LLM-as-a-Judge Oracle for evaluating agent solutions against expected root causes."""

import json
import logging
import os
import re
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from clients.stratus.llm_backend.get_llm_backend import LiteLLMBackend

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()


class JudgmentResult(str, Enum):
    """Possible judgment results from the LLM Judge."""

    TRUE = "True"  # Correct diagnosis
    FALSE = "False"  # Incorrect diagnosis
    FALSE_POSITIVE = "FalsePositive"  # Identified a problem when there isn't one
    FALSE_NEGATIVE = "FalseNegative"  # Missed a problem that exists


class LLMJudge:
    """Judge that uses LiteLLM backend to evaluate agent solutions."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ):
        """Initialize the LLM Judge with LiteLLM backend.

        Args:
            provider: LLM provider (e.g., "openai", "litellm", "compatible")
            model_name: Model name/ID to use
            url: API endpoint URL (for compatible providers)
            api_key: API key for authentication
            temperature: Sampling temperature (default: 0.0 for deterministic)
            max_tokens: Maximum tokens in response
        """
        # Load from environment if not provided
        self.provider = provider or os.getenv("PROVIDER", "openai")
        self.model_name = model_name or os.getenv("MODEL_TOOLS", "gpt-4o")
        self.url = url or os.getenv("URL_TOOLS", "")
        self.api_key = api_key or os.getenv("API_KEY_TOOLS", "")
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Initialize LiteLLM backend
        self.backend = LiteLLMBackend(
            provider=self.provider,
            model_name=self.model_name,
            url=self.url,
            api_key=self.api_key,
            api_version=os.getenv("API_VERSION_TOOLS", ""),
            seed=int(os.getenv("SEED_TOOLS", "42")),
            top_p=float(os.getenv("TOP_P_TOOLS", "0.95")),
            temperature=self.temperature,
            reasoning_effort="",
            thinking_tools="",
            thinking_budget_tools=0,
            max_tokens=self.max_tokens,
        )

        logger.info(f"Initialized LLMJudge with provider={self.provider}, model={self.model_name}")

    def judge(self, solution: str, expectation: str) -> JudgmentResult:
        """Judge whether the agent's solution matches the expected root cause.

        Args:
            solution: The agent's answer/diagnosis
            expectation: The expected root cause (ground truth). Empty string means no fault exists.

        Returns:
            JudgmentResult: One of True, False, FalsePositive, or FalseNegative
        """
        # Construct the prompt for the LLM
        system_prompt = """You are an expert judge evaluating whether an agent's diagnosis of a system issue matches the expected root cause.

Your task is to compare the agent's answer with the expected root cause and determine if they are semantically equivalent.

Classification criteria:
- **True**: The agent correctly identified the root cause. The diagnosis captures the essential problem even if worded differently.
- **False**: The agent identified a different problem or misdiagnosed the root cause.
- **FalsePositive**: The expected root cause is empty (no fault exists), but the agent reported a problem.
- **FalseNegative**: The expected root cause describes a real fault, but the agent reported no issues or said everything is normal.

You must respond with EXACTLY ONE of these four values: True, False, FalsePositive, or FalseNegative

Your response should be in the following JSON format:
{
    "judgment": "True|False|FalsePositive|FalseNegative",
    "reasoning": "Brief explanation of why you made this judgment"
}"""

        user_prompt = f"""Expected Root Cause:
{expectation if expectation else "(No fault - system is operating normally)"}

Agent's Answer:
{solution}

Evaluate whether the agent's answer correctly identifies the root cause. Respond in JSON format with your judgment and reasoning."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            # Get response from LLM
            response = self.backend.inference(messages)
            response_text = response.content.strip()

            logger.info(f"LLM Response: {response_text}")

            # Parse the response
            judgment = self._parse_judgment(response_text)
            logger.info(f"Parsed judgment: {judgment}")

            return judgment

        except Exception as e:
            logger.error(f"Error during judgment: {e}")
            raise

    def _parse_judgment(self, response_text: str) -> JudgmentResult:
        """Parse the LLM response to extract the judgment.

        Args:
            response_text: Raw response from the LLM

        Returns:
            JudgmentResult: Parsed judgment

        Raises:
            ValueError: If response cannot be parsed
        """
        # Try to parse as JSON first
        try:
            # Remove markdown code blocks if present
            clean_text = re.sub(r"```json\s*|\s*```", "", response_text)
            clean_text = clean_text.strip()

            response_json = json.loads(clean_text)
            judgment_str = response_json.get("judgment", "").strip()
            reasoning = response_json.get("reasoning", "")

            logger.info(f"Reasoning: {reasoning}")

        except json.JSONDecodeError:
            # Fallback: try to extract judgment directly from text
            logger.warning("Failed to parse JSON, attempting direct extraction")
            judgment_str = response_text

        # Normalize the judgment string
        judgment_str = judgment_str.strip().lower()

        # Map to JudgmentResult
        if judgment_str == "true":
            return JudgmentResult.TRUE
        elif judgment_str == "false":
            return JudgmentResult.FALSE
        elif judgment_str in ["falsepositive", "false positive"]:
            return JudgmentResult.FALSE_POSITIVE
        elif judgment_str in ["falsenegative", "false negative"]:
            return JudgmentResult.FALSE_NEGATIVE
        else:
            raise ValueError(f"Could not parse judgment from response: {response_text}")


def load_test_data(yaml_path: str) -> list[dict]:
    """Load test data from YAML file.

    Args:
        yaml_path: Path to the YAML file

    Returns:
        List of test cases with 'description', 'answer', and 'oracle' fields
    """
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    return data


def main():
    """Main function to test the LLM Judge with data from data.yaml."""
    # Get the directory of this script
    script_dir = Path(__file__).parent
    data_path = script_dir / "data.yaml"

    if not data_path.exists():
        logger.error(f"Test data file not found: {data_path}")
        return

    # Load test data
    test_cases = load_test_data(str(data_path))
    logger.info(f"Loaded {len(test_cases)} test cases from {data_path}")

    # Initialize judge
    judge = LLMJudge()

    # Track results
    total_cases = len(test_cases)
    correct = 0
    incorrect = 0
    results = []

    # Evaluate each test case
    for i, test_case in enumerate(test_cases, 1):
        description = test_case.get("description", "")
        answer = test_case.get("answer", "")
        expected_judgment = test_case.get("oracle", "")

        logger.info(f"\n{'='*80}")
        logger.info(f"Test Case {i}/{total_cases}")
        logger.info(
            f"Expected Root Cause: {description[:100]}..."
            if len(description) > 100
            else f"Expected Root Cause: {description}"
        )
        logger.info(f"Agent Answer: {answer[:100]}..." if len(answer) > 100 else f"Agent Answer: {answer}")
        logger.info(f"Expected Judgment: {expected_judgment}")

        try:
            # Get judgment from LLM
            actual_judgment = judge.judge(solution=answer, expectation=description)

            # Normalize expected judgment for comparison
            expected_normalized = expected_judgment.strip().lower().replace(" ", "")
            actual_normalized = actual_judgment.value.lower().replace(" ", "")

            is_correct = expected_normalized == actual_normalized

            if is_correct:
                correct += 1
                status = " CORRECT"
            else:
                incorrect += 1
                status = " INCORRECT"

            logger.info(f"Actual Judgment: {actual_judgment.value}")
            logger.info(f"Status: {status}")

            results.append(
                {
                    "test_case": i,
                    "expected": expected_judgment,
                    "actual": actual_judgment.value,
                    "correct": is_correct,
                }
            )

        except Exception as e:
            logger.error(f"Error processing test case {i}: {e}")
            incorrect += 1
            results.append(
                {
                    "test_case": i,
                    "expected": expected_judgment,
                    "actual": f"ERROR: {str(e)}",
                    "correct": False,
                }
            )

    # Print summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Total test cases: {total_cases}")
    logger.info(f"Correct: {correct} ({correct/total_cases*100:.1f}%)")
    logger.info(f"Incorrect: {incorrect} ({incorrect/total_cases*100:.1f}%)")
    logger.info(f"\nDetailed Results:")

    for result in results:
        status_symbol = "" if result["correct"] else ""
        logger.info(
            f"  {status_symbol} Case {result['test_case']}: Expected={result['expected']}, Actual={result['actual']}"
        )


if __name__ == "__main__":
    main()
