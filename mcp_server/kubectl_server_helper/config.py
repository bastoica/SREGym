from pydantic import BaseModel, Field, field_validator
from pathlib import Path
import os

current_dir = Path(__file__).resolve().parent


class KubectlToolCfg(BaseModel):
    retry_wait_time: float = Field(
        default=60,
        description="Seconds to wait between retries.",
        gt=0
    )

    forbid_unsafe_commands: bool = Field(
        default=False,
        description="Forbid unsafe commands in the rollback tool.",
    )

    verify_dry_run: bool = Field(
        default=False,
        description="Enable verification of dry run results.",
    )

    # update the output dir with session id if using remote mcp server
    output_dir: str = Field(
        default=str(current_dir / "data"),
        description="Directory to store some data used by kubectl server."
    )

    namespace: str = Field(
        default="",
        description="Kubernetes namespace to use for the agent.",
    )

    use_rollback_stack: bool = Field(
        default=True,
        description="Enable rollback stack for the rollback tool.",
    )

    """ Rollback Tool Configuration """
    validate_rollback: bool = Field(
        default=False,
        description="Enable generation of validation information",
    )

    clear_replicaset: bool = Field(
        default=True,
        description="Enable clearing of replicaset after rolling back deployment.",
    )  # Warning: This part may be harmful to the system. Use with caution.

    clear_rs_wait_time: float = Field(
        default=5,
        description="Seconds to wait before clearing replicaset.",
    )

    @classmethod
    @field_validator("output_dir")
    def name_must_not_be_empty(cls, v):
        output_dir = v
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        if not os.access(output_dir, os.W_OK):
            raise PermissionError(f"Output directory {output_dir} is not writable.")
        return output_dir

