import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


def str_to_bool(s: str) -> bool:
    """
    Convert a string to a boolean value.

    True values: 'true', '1', 'yes', 'y', 'on'
    False values: 'false', '0', 'no', 'n', 'off'

    Raises:
        ValueError: if the string does not represent a boolean.

    Args:
        s (str): The string to convert.

    Returns:
        bool: The converted boolean value.
    """
    if not isinstance(s, str):
        raise TypeError("Input must be a string.")

    true_values = {'true', '1', 'yes', 'y', 'on'}
    false_values = {'false', '0', 'no', 'n', 'off'}

    s_lower = s.strip().lower()
    if s_lower in true_values:
        return True
    elif s_lower in false_values:
        return False
    else:
        raise ValueError(f"Invalid literal for boolean: '{s}'")


class StratusAgentDemoCfg(BaseModel):
    is_retry_enabled: bool = Field(
        default=str_to_bool(os.environ["IS_RETRY_ENABLED"]),
        description="Set true to enable retry mechanism for mitigation task"
    )

    max_retry_count: int = Field(
        default=int(os.environ["MAX_RETRY_COUNT"]),
        description="Maximum retry count for mitigation task",
    )

    time_to_wait_before_evaluation: int = Field(
        default=int(os.environ["TIME_TO_WAIT_BEFORE_EVALUATION"]),
        description="Time to wait before evaluating the system after mitigation",
    )

    last_n_round_reflections: int = Field(
        default=int(os.environ["LAST_N_ROUND_REFLECTIONS"]),
        description="Number of previous reflections to include in the mitigation task",
    )

