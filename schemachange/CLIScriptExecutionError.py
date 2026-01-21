"""Custom exception for CLI script execution failures with rich context."""

from __future__ import annotations

from pathlib import Path


class CLIScriptExecutionError(Exception):
    """
    Exception raised when a CLI script execution fails.

    Captures rich context about the failure including script details,
    CLI tool information, exit codes, and output for debugging.
    """

    def __init__(
        self,
        script_name: str,
        script_path: Path,
        script_type: str,
        error_message: str,
        cli_tool: str | None = None,
        command: str | None = None,
        exit_code: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        step_index: int | None = None,
        original_exception: Exception | None = None,
    ):
        """
        Initialize CLIScriptExecutionError with rich context.

        Args:
            script_name: Name of the script that failed
            script_path: Path to the script file
            script_type: Type of script (V, R, or A)
            error_message: Human-readable error message
            cli_tool: CLI tool that was being executed (e.g., "snow")
            command: The CLI command that failed
            exit_code: Process exit code
            stdout: Captured stdout from the process
            stderr: Captured stderr from the process
            step_index: Index of the step that failed (0-based)
            original_exception: The original exception that was raised
        """
        self.script_name = script_name
        self.script_path = script_path
        self.script_type = script_type
        self.error_message = error_message
        self.cli_tool = cli_tool
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.step_index = step_index
        self.original_exception = original_exception

        # Create user-friendly message
        step_info = f" (step {step_index + 1})" if step_index is not None else ""
        super().__init__(f"Failed to execute {script_type} CLI script '{script_name}'{step_info}: {error_message}")

    def get_structured_error(self) -> dict:
        """
        Get error details as structured dict for logging.

        Returns:
            Dictionary with error details suitable for structured logging
        """
        return {
            "script_name": self.script_name,
            "script_path": self.script_path.as_posix(),
            "script_type": self.script_type,
            "error_message": self.error_message,
            "cli_tool": self.cli_tool,
            "command": self.command,
            "exit_code": self.exit_code,
            "step_index": self.step_index,
        }
