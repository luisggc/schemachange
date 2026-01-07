from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import jinja2
import jinja2.ext
import structlog
from jinja2.loaders import BaseLoader

from schemachange.JinjaEnvVar import JinjaEnvVar

logger = structlog.getLogger(__name__)


class JinjaTemplateProcessor:
    _env_args = {
        "undefined": jinja2.StrictUndefined,
        "autoescape": False,
        "extensions": [JinjaEnvVar],
    }

    def __init__(self, project_root: Path, modules_folder: Path = None):
        loader: BaseLoader
        if modules_folder:
            loader = jinja2.ChoiceLoader(
                [
                    jinja2.FileSystemLoader(project_root),
                    jinja2.PrefixLoader({"modules": jinja2.FileSystemLoader(modules_folder)}),
                ]
            )
        else:
            loader = jinja2.FileSystemLoader(project_root)
        self.__environment = jinja2.Environment(loader=loader, **self._env_args)
        self.__project_root = project_root

    def list(self):
        return self.__environment.list_templates()

    def override_loader(self, loader: jinja2.BaseLoader):
        # to make unit testing easier
        self.__environment = jinja2.Environment(loader=loader, **self._env_args)

    def render(self, script: str, variables: dict[str, Any] | None) -> str:
        if not variables:
            variables = {}
        # jinja needs posix path
        posix_path = Path(script).as_posix()
        template = self.__environment.get_template(posix_path)
        raw_content = template.render(**variables)

        # Remove UTF-8 BOM if present (issue #250)
        if raw_content.startswith("\ufeff"):
            logger.debug("Removing UTF-8 BOM from script", script=script)
            raw_content = raw_content[1:]

        content = raw_content.strip()

        # Validate content is not empty after processing
        if not content or content.isspace():
            raise ValueError(
                f"Script '{script}' rendered to empty content. Check Jinja variables and conditional blocks."
            )

        # Check if content is only comments (would fail in Snowflake)
        content_without_comments = re.sub(r"--[^\n]*", "", content)
        content_without_comments = re.sub(r"/\*.*?\*/", "", content_without_comments, flags=re.DOTALL)
        content_without_comments = content_without_comments.replace(";", "").strip()

        if not content_without_comments:
            raise ValueError(
                f"Script '{script}' contains only comments or semicolons. Add SQL statements or remove the script."
            )

        return content

    def relpath(self, file_path: Path):
        return file_path.relative_to(self.__project_root)
