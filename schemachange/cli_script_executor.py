"""CLI Script Executor for running CLI commands defined in .cli.yml migration files."""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import structlog
import yaml

from schemachange.CLIScriptExecutionError import CLIScriptExecutionError
from schemachange.session.Script import Script

logger = structlog.getLogger(__name__)

# Allowed CLI tools (initially only Snowflake CLI)
ALLOWED_CLI_TOOLS = frozenset({"snow"})


def _resolve_cli_tool(cli: str) -> str:
    """
    Resolve a CLI tool name or path to an executable path.

    Validates that the tool is in ALLOWED_CLI_TOOLS (by basename if full path provided).
    For simple names like 'snow', uses shutil.which() to find the full path.

    Args:
        cli: CLI tool name (e.g., 'snow') or full path (e.g., '/usr/bin/snow')

    Returns:
        Resolved path to the executable

    Raises:
        ValueError: If the tool is not in ALLOWED_CLI_TOOLS or not found
    """
    # Check if it's a path (contains path separator)
    if os.sep in cli or (os.altsep and os.altsep in cli):
        # It's a full/relative path - validate basename against allowed tools
        basename = Path(cli).name
        if basename not in ALLOWED_CLI_TOOLS:
            raise ValueError(
                f"CLI tool '{basename}' (from path '{cli}') is not supported. "
                f"Allowed tools: {', '.join(sorted(ALLOWED_CLI_TOOLS))}"
            )
        # Verify the path exists
        if not Path(cli).exists():
            raise ValueError(f"CLI tool path '{cli}' does not exist")
        return cli
    else:
        # It's a simple name - validate against allowed tools
        if cli not in ALLOWED_CLI_TOOLS:
            raise ValueError(
                f"CLI tool '{cli}' is not supported. Allowed tools: {', '.join(sorted(ALLOWED_CLI_TOOLS))}"
            )
        # Resolve to full path using shutil.which
        resolved = shutil.which(cli)
        if resolved is None:
            raise ValueError(f"CLI tool '{cli}' not found in PATH. Please ensure it is installed and accessible.")
        return resolved


@dataclasses.dataclass(frozen=True)
class CLIStep:
    """Represents a single CLI command step in a CLI migration script."""

    cli: str  # Original CLI name from YAML (e.g., 'snow')
    cli_path: str  # Resolved full path to executable
    command: str
    args: tuple[str, ...] = ()
    working_dir: Path | None = None
    env: dict[str, str] | None = None
    description: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], root_folder: Path) -> CLIStep:
        """
        Create a CLIStep from a dictionary parsed from YAML.

        Args:
            data: Dictionary containing step configuration
            root_folder: Root folder for resolving relative working directories

        Returns:
            CLIStep instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Validate required fields
        if "cli" not in data:
            raise ValueError("Step is missing required field 'cli'")
        if "command" not in data:
            raise ValueError("Step is missing required field 'command'")

        cli = data["cli"]
        # Resolve and validate the CLI tool
        cli_path = _resolve_cli_tool(cli)

        # Parse arguments
        args = data.get("args", [])
        if isinstance(args, str):
            args = [args]
        args = tuple(str(arg) for arg in args)

        # Parse working directory (relative to root_folder, resolved to absolute)
        working_dir = None
        if "working_dir" in data and data["working_dir"]:
            working_dir = (root_folder / data["working_dir"]).resolve()
            if not working_dir.exists():
                raise ValueError(f"Working directory '{working_dir}' does not exist")
            if not working_dir.is_dir():
                raise ValueError(f"Working directory '{working_dir}' is not a directory")

        # Parse environment variables
        env = None
        if "env" in data and data["env"]:
            env = {str(k): str(v) for k, v in data["env"].items()}

        return cls(
            cli=cli,
            cli_path=cli_path,
            command=data["command"],
            args=args,
            working_dir=working_dir,
            env=env,
            description=data.get("description"),
        )


def parse_cli_script(content: str, root_folder: Path) -> list[CLIStep]:
    """
    Parse CLI script YAML content into a list of CLIStep objects.

    Args:
        content: Rendered YAML content
        root_folder: Root folder for resolving relative paths

    Returns:
        List of CLIStep objects

    Raises:
        ValueError: If YAML is invalid or schema doesn't match expected format
    """
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in CLI script: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("CLI script must be a YAML dictionary with a 'steps' key")

    if "steps" not in data:
        raise ValueError("CLI script is missing required 'steps' key")

    steps_data = data["steps"]
    if not isinstance(steps_data, list):
        raise ValueError("'steps' must be a list of step definitions")

    if not steps_data:
        raise ValueError("'steps' list cannot be empty")

    steps = []
    for i, step_data in enumerate(steps_data):
        try:
            step = CLIStep.from_dict(step_data, root_folder)
            steps.append(step)
        except ValueError as e:
            raise ValueError(f"Invalid step at index {i}: {e}") from e

    return steps


def execute_cli_step(
    step: CLIStep,
    step_index: int,
    script: Script,
    dry_run: bool,
    log: structlog.BoundLogger,
) -> subprocess.CompletedProcess | None:
    """
    Execute a single CLI step.

    Args:
        step: CLIStep to execute
        step_index: Index of the step (for logging)
        script: The parent script object
        dry_run: If True, log the command without executing
        log: Logger instance

    Returns:
        CompletedProcess if executed, None if dry_run

    Raises:
        CLIScriptExecutionError: If the command fails
    """
    # Build the full command using the resolved path
    cmd_parts = [step.cli_path, *step.command.split(), *step.args]
    # Use original cli name for display/logging
    cmd_str = " ".join([step.cli, *step.command.split(), *step.args])

    step_log = log.bind(
        step_index=step_index + 1,
        cli=step.cli,
        command=step.command,
        working_dir=step.working_dir.as_posix() if step.working_dir else None,
    )

    if step.description:
        step_log = step_log.bind(step_description=step.description)

    if dry_run:
        step_log.info("Dry run - would execute CLI command", command=cmd_str)
        return None

    step_log.info("Executing CLI command", command=cmd_str)
    step_log.debug(
        "CLI execution details",
        cli_path=step.cli_path,
        cmd_parts=cmd_parts,
        cwd=str(step.working_dir) if step.working_dir else None,
    )

    # Prepare environment
    env = os.environ.copy()
    if step.env:
        env.update(step.env)

    # Determine working directory
    cwd = step.working_dir if step.working_dir else None

    try:
        result = subprocess.run(
            cmd_parts,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,  # We'll handle errors ourselves
        )

        # Log output
        if result.stdout:
            step_log.debug("CLI stdout", output=result.stdout.strip())

        if result.stderr:
            step_log.debug("CLI stderr", output=result.stderr.strip())

        # Check for failure
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else f"Command exited with code {result.returncode}"
            step_log.error(
                "CLI command failed",
                exit_code=result.returncode,
                stderr=result.stderr[:500] if result.stderr else None,
            )
            raise CLIScriptExecutionError(
                script_name=script.name,
                script_path=script.file_path,
                script_type=script.type,
                error_message=error_msg,
                cli_tool=step.cli,
                command=cmd_str,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                step_index=step_index,
            )

        step_log.info("CLI command completed successfully", exit_code=0)
        return result

    except FileNotFoundError as e:
        step_log.error(
            "File not found during CLI execution",
            cli=step.cli,
            cli_path=step.cli_path,
            cmd_parts=cmd_parts,
            cwd=str(step.working_dir) if step.working_dir else None,
            original_error=str(e),
        )
        raise CLIScriptExecutionError(
            script_name=script.name,
            script_path=script.file_path,
            script_type=script.type,
            error_message=f"File not found during CLI execution: {e}. CLI path: {step.cli_path}, working_dir: {step.working_dir}",
            cli_tool=step.cli,
            command=cmd_str,
            step_index=step_index,
            original_exception=e,
        ) from e

    except PermissionError as e:
        step_log.error("Permission denied executing CLI tool", cli=step.cli)
        raise CLIScriptExecutionError(
            script_name=script.name,
            script_path=script.file_path,
            script_type=script.type,
            error_message=f"Permission denied executing '{step.cli}'",
            cli_tool=step.cli,
            command=cmd_str,
            step_index=step_index,
            original_exception=e,
        ) from e

    except Exception as e:
        step_log.error("Unexpected error executing CLI command", error=str(e))
        raise CLIScriptExecutionError(
            script_name=script.name,
            script_path=script.file_path,
            script_type=script.type,
            error_message=f"Unexpected error: {str(e)}",
            cli_tool=step.cli,
            command=cmd_str,
            step_index=step_index,
            original_exception=e,
        ) from e


def execute_cli_script(
    script: Script,
    content: str,
    root_folder: Path,
    dry_run: bool,
    log: structlog.BoundLogger,
) -> int:
    """
    Execute a CLI migration script.

    Args:
        script: The CLI script object
        content: Rendered YAML content (after Jinja processing)
        root_folder: Root folder for resolving relative paths
        dry_run: If True, log commands without executing
        log: Logger instance

    Returns:
        Total execution time in seconds

    Raises:
        ValueError: If the script content is invalid
        CLIScriptExecutionError: If any step fails
    """
    script_log = log.bind(
        script_name=script.name,
        script_format="CLI",
    )

    script_log.info("Executing CLI migration script")

    # Parse the YAML content
    try:
        steps = parse_cli_script(content, root_folder)
    except ValueError as e:
        script_log.error("Failed to parse CLI script", error=str(e))
        raise

    script_log.debug("Parsed CLI script", step_count=len(steps))

    if dry_run:
        script_log.info("Running in dry-run mode. Commands will be logged but not executed.")

    # Execute each step
    start_time = time.time()
    for i, step in enumerate(steps):
        execute_cli_step(
            step=step,
            step_index=i,
            script=script,
            dry_run=dry_run,
            log=script_log,
        )

    execution_time = round(time.time() - start_time)

    script_log.info(
        "CLI migration script completed",
        steps_executed=len(steps),
        execution_time_seconds=execution_time,
    )

    return execution_time
