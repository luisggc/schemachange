"""Tests for CLI script executor functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import structlog

from schemachange.cli_script_executor import (
    ALLOWED_CLI_TOOLS,
    CLIStep,
    _resolve_cli_tool,
    execute_cli_script,
    execute_cli_step,
    parse_cli_script,
)
from schemachange.CLIScriptExecutionError import CLIScriptExecutionError
from schemachange.session.Script import VersionedCLIScript

# Mock snow path for tests
MOCK_SNOW_PATH = "/usr/local/bin/snow"


@pytest.fixture(autouse=True)
def mock_shutil_which():
    """Mock shutil.which to return a consistent path for 'snow'."""
    with patch("schemachange.cli_script_executor.shutil.which") as mock_which:
        mock_which.return_value = MOCK_SNOW_PATH
        yield mock_which


class TestResolveCLITool:
    def test_resolve_simple_name(self, mock_shutil_which):
        result = _resolve_cli_tool("snow")
        assert result == MOCK_SNOW_PATH
        mock_shutil_which.assert_called_once_with("snow")

    def test_resolve_full_path(self, mock_shutil_which):
        with patch("schemachange.cli_script_executor.Path.exists", return_value=True):
            result = _resolve_cli_tool("/custom/path/to/snow")
        assert result == "/custom/path/to/snow"
        mock_shutil_which.assert_not_called()

    def test_resolve_unsupported_tool_raises_error(self, mock_shutil_which):
        with pytest.raises(ValueError) as e:
            _resolve_cli_tool("unsupported_tool")
        assert "not supported" in str(e.value)

    def test_resolve_tool_not_found_raises_error(self, mock_shutil_which):
        mock_shutil_which.return_value = None
        with pytest.raises(ValueError) as e:
            _resolve_cli_tool("snow")
        assert "not found in PATH" in str(e.value)

    def test_resolve_full_path_not_exists_raises_error(self, mock_shutil_which):
        with patch("schemachange.cli_script_executor.Path.exists", return_value=False):
            with pytest.raises(ValueError) as e:
                _resolve_cli_tool("/nonexistent/path/snow")
        assert "does not exist" in str(e.value)


class TestCLIStep:
    def test_from_dict_minimal(self):
        data = {"cli": "snow", "command": "app deploy"}
        step = CLIStep.from_dict(data, Path("/root"))

        assert step.cli == "snow"
        assert step.cli_path == MOCK_SNOW_PATH
        assert step.command == "app deploy"
        assert step.args == ()
        assert step.working_dir is None
        assert step.env is None
        assert step.description is None

    def test_from_dict_full(self, tmp_path):
        # Create a real directory for working_dir validation
        working_dir = tmp_path / "my-app"
        working_dir.mkdir()

        data = {
            "cli": "snow",
            "command": "app deploy",
            "args": ["--prune", "--recursive"],
            "working_dir": str(working_dir),
            "env": {"MY_VAR": "value"},
            "description": "Deploy the app",
        }
        step = CLIStep.from_dict(data, tmp_path)

        assert step.cli == "snow"
        assert step.cli_path == MOCK_SNOW_PATH
        assert step.command == "app deploy"
        assert step.args == ("--prune", "--recursive")
        assert step.working_dir == working_dir
        assert step.env == {"MY_VAR": "value"}
        assert step.description == "Deploy the app"

    def test_from_dict_string_args(self):
        data = {"cli": "snow", "command": "app deploy", "args": "--force"}
        step = CLIStep.from_dict(data, Path("/root"))

        assert step.args == ("--force",)

    def test_from_dict_missing_cli_raises_error(self):
        data = {"command": "app deploy"}
        with pytest.raises(ValueError) as e:
            CLIStep.from_dict(data, Path("/root"))
        assert "missing required field 'cli'" in str(e.value)

    def test_from_dict_missing_command_raises_error(self):
        data = {"cli": "snow"}
        with pytest.raises(ValueError) as e:
            CLIStep.from_dict(data, Path("/root"))
        assert "missing required field 'command'" in str(e.value)

    def test_from_dict_unsupported_cli_raises_error(self):
        data = {"cli": "unsupported_tool", "command": "do something"}
        with pytest.raises(ValueError) as e:
            CLIStep.from_dict(data, Path("/root"))
        assert "not supported" in str(e.value)
        assert "unsupported_tool" in str(e.value)

    def test_from_dict_nonexistent_working_dir_raises_error(self, tmp_path):
        data = {
            "cli": "snow",
            "command": "app deploy",
            "working_dir": "./nonexistent-dir",
        }
        with pytest.raises(ValueError) as e:
            CLIStep.from_dict(data, tmp_path)
        assert "does not exist" in str(e.value)

    def test_from_dict_working_dir_is_file_raises_error(self, tmp_path):
        # Create a file instead of a directory
        file_path = tmp_path / "not-a-dir"
        file_path.write_text("I'm a file")

        data = {
            "cli": "snow",
            "command": "app deploy",
            "working_dir": str(file_path),
        }
        with pytest.raises(ValueError) as e:
            CLIStep.from_dict(data, tmp_path)
        assert "is not a directory" in str(e.value)


class TestParseCLIScript:
    def test_parse_valid_single_step(self):
        content = """
steps:
  - cli: snow
    command: app deploy
"""
        steps = parse_cli_script(content, Path("/root"))

        assert len(steps) == 1
        assert steps[0].cli == "snow"
        assert steps[0].command == "app deploy"

    def test_parse_valid_multiple_steps(self, tmp_path):
        # Create directories for working_dir validation
        app1_dir = tmp_path / "app1"
        app1_dir.mkdir()
        snowpark_dir = tmp_path / "snowpark"
        snowpark_dir.mkdir()

        content = """
steps:
  - cli: snow
    command: app deploy
    working_dir: ./app1
  - cli: snow
    command: snowpark deploy
    working_dir: ./snowpark
"""
        steps = parse_cli_script(content, tmp_path)

        assert len(steps) == 2
        assert steps[0].command == "app deploy"
        assert steps[0].working_dir == app1_dir
        assert steps[1].command == "snowpark deploy"
        assert steps[1].working_dir == snowpark_dir

    def test_parse_invalid_yaml_raises_error(self):
        content = "this is not: valid: yaml: ::::"
        with pytest.raises(ValueError) as e:
            parse_cli_script(content, Path("/root"))
        assert "Invalid YAML" in str(e.value)

    def test_parse_missing_steps_key_raises_error(self):
        content = """
cli: snow
command: app deploy
"""
        with pytest.raises(ValueError) as e:
            parse_cli_script(content, Path("/root"))
        assert "missing required 'steps' key" in str(e.value)

    def test_parse_steps_not_list_raises_error(self):
        content = """
steps:
  cli: snow
  command: app deploy
"""
        with pytest.raises(ValueError) as e:
            parse_cli_script(content, Path("/root"))
        assert "'steps' must be a list" in str(e.value)

    def test_parse_empty_steps_raises_error(self):
        content = """
steps: []
"""
        with pytest.raises(ValueError) as e:
            parse_cli_script(content, Path("/root"))
        assert "'steps' list cannot be empty" in str(e.value)

    def test_parse_invalid_step_raises_error_with_index(self):
        content = """
steps:
  - cli: snow
    command: app deploy
  - cli: snow
"""
        with pytest.raises(ValueError) as e:
            parse_cli_script(content, Path("/root"))
        assert "Invalid step at index 1" in str(e.value)


class TestExecuteCLIStep:
    @pytest.fixture
    def mock_script(self):
        return VersionedCLIScript(
            name="V1.0.0__deploy.cli.yml",
            file_path=Path("/scripts/V1.0.0__deploy.cli.yml"),
            description="Deploy",
            version="1.0.0",
        )

    @pytest.fixture
    def mock_logger(self):
        return structlog.get_logger()

    def test_dry_run_does_not_execute(self, mock_script, mock_logger):
        step = CLIStep(cli="snow", cli_path=MOCK_SNOW_PATH, command="app deploy")

        with patch("schemachange.cli_script_executor.subprocess.run") as mock_run:
            result = execute_cli_step(step, 0, mock_script, dry_run=True, log=mock_logger)

        mock_run.assert_not_called()
        assert result is None

    def test_successful_execution(self, mock_script, mock_logger):
        step = CLIStep(cli="snow", cli_path=MOCK_SNOW_PATH, command="app deploy")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Deployed successfully"
        mock_result.stderr = ""

        with patch("schemachange.cli_script_executor.subprocess.run", return_value=mock_result) as mock_run:
            result = execute_cli_step(step, 0, mock_script, dry_run=False, log=mock_logger)

        mock_run.assert_called_once()
        assert result.returncode == 0

    def test_failed_execution_raises_error(self, mock_script, mock_logger):
        step = CLIStep(cli="snow", cli_path=MOCK_SNOW_PATH, command="app deploy")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: deployment failed"

        with patch("schemachange.cli_script_executor.subprocess.run", return_value=mock_result):
            with pytest.raises(CLIScriptExecutionError) as e:
                execute_cli_step(step, 0, mock_script, dry_run=False, log=mock_logger)

        assert e.value.exit_code == 1
        assert e.value.cli_tool == "snow"
        assert e.value.step_index == 0

    def test_cli_not_found_raises_error(self, mock_script, mock_logger):
        step = CLIStep(cli="snow", cli_path=MOCK_SNOW_PATH, command="app deploy")

        with patch("schemachange.cli_script_executor.subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(CLIScriptExecutionError) as e:
                execute_cli_step(step, 0, mock_script, dry_run=False, log=mock_logger)

        assert "not found" in str(e.value.error_message)

    def test_step_with_working_dir(self, mock_script, mock_logger):
        step = CLIStep(cli="snow", cli_path=MOCK_SNOW_PATH, command="app deploy", working_dir=Path("/my/app"))

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("schemachange.cli_script_executor.subprocess.run", return_value=mock_result) as mock_run:
            execute_cli_step(step, 0, mock_script, dry_run=False, log=mock_logger)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == Path("/my/app")

    def test_step_with_env_vars(self, mock_script, mock_logger):
        step = CLIStep(cli="snow", cli_path=MOCK_SNOW_PATH, command="app deploy", env={"MY_VAR": "value"})

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("schemachange.cli_script_executor.subprocess.run", return_value=mock_result) as mock_run:
            with patch.dict("os.environ", {"EXISTING": "var"}, clear=True):
                execute_cli_step(step, 0, mock_script, dry_run=False, log=mock_logger)

        call_kwargs = mock_run.call_args[1]
        assert "MY_VAR" in call_kwargs["env"]
        assert call_kwargs["env"]["MY_VAR"] == "value"


class TestExecuteCLIScript:
    @pytest.fixture
    def mock_script(self):
        return VersionedCLIScript(
            name="V1.0.0__deploy.cli.yml",
            file_path=Path("/scripts/V1.0.0__deploy.cli.yml"),
            description="Deploy",
            version="1.0.0",
        )

    @pytest.fixture
    def mock_logger(self):
        return structlog.get_logger()

    def test_execute_single_step_script(self, mock_script, mock_logger):
        content = """
steps:
  - cli: snow
    command: app deploy
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""

        with patch("schemachange.cli_script_executor.subprocess.run", return_value=mock_result):
            execution_time = execute_cli_script(
                script=mock_script,
                content=content,
                root_folder=Path("/root"),
                dry_run=False,
                log=mock_logger,
            )

        assert execution_time >= 0

    def test_execute_dry_run(self, mock_script, mock_logger):
        content = """
steps:
  - cli: snow
    command: app deploy
"""
        with patch("schemachange.cli_script_executor.subprocess.run") as mock_run:
            execution_time = execute_cli_script(
                script=mock_script,
                content=content,
                root_folder=Path("/root"),
                dry_run=True,
                log=mock_logger,
            )

        mock_run.assert_not_called()
        assert execution_time >= 0

    def test_execute_invalid_yaml_raises_error(self, mock_script, mock_logger):
        content = "not valid yaml :::"

        with pytest.raises(ValueError):
            execute_cli_script(
                script=mock_script,
                content=content,
                root_folder=Path("/root"),
                dry_run=False,
                log=mock_logger,
            )

    def test_execute_step_failure_stops_execution(self, mock_script, mock_logger):
        content = """
steps:
  - cli: snow
    command: step1
  - cli: snow
    command: step2
"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error"

        with patch("schemachange.cli_script_executor.subprocess.run", return_value=mock_result):
            with pytest.raises(CLIScriptExecutionError) as e:
                execute_cli_script(
                    script=mock_script,
                    content=content,
                    root_folder=Path("/root"),
                    dry_run=False,
                    log=mock_logger,
                )

        # Should fail on first step
        assert e.value.step_index == 0


class TestCLIScriptExecutionError:
    def test_error_message_includes_step_info(self):
        error = CLIScriptExecutionError(
            script_name="V1.0.0__deploy.cli.yml",
            script_path=Path("/scripts/V1.0.0__deploy.cli.yml"),
            script_type="V",
            error_message="Command failed",
            step_index=2,
        )

        assert "step 3" in str(error)  # 0-indexed, so step 2 is displayed as step 3

    def test_get_structured_error(self):
        error = CLIScriptExecutionError(
            script_name="V1.0.0__deploy.cli.yml",
            script_path=Path("/scripts/V1.0.0__deploy.cli.yml"),
            script_type="V",
            error_message="Command failed",
            cli_tool="snow",
            command="snow app deploy",
            exit_code=1,
            step_index=0,
        )

        structured = error.get_structured_error()

        assert structured["script_name"] == "V1.0.0__deploy.cli.yml"
        assert structured["cli_tool"] == "snow"
        assert structured["exit_code"] == 1
        assert structured["step_index"] == 0


class TestAllowedCLITools:
    def test_snow_is_allowed(self):
        assert "snow" in ALLOWED_CLI_TOOLS

    def test_only_snow_is_allowed_initially(self):
        # Per design doc, only snow is supported initially
        assert ALLOWED_CLI_TOOLS == frozenset({"snow"})
