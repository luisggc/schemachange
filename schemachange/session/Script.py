from __future__ import annotations

import dataclasses
import re
from abc import ABC
from pathlib import Path
from re import Pattern
from typing import (
    ClassVar,
    Literal,
    TypeVar,
)

import structlog

logger = structlog.getLogger(__name__)
T = TypeVar("T", bound="Script")


@dataclasses.dataclass(frozen=True)
class Script(ABC):
    pattern: ClassVar[Pattern[str]]
    type: ClassVar[Literal["V", "R", "A"]]
    format: ClassVar[Literal["SQL", "CLI"]] = "SQL"
    name: str
    file_path: Path
    description: str

    @property
    def type_desc(self) -> str:
        """Return a descriptive string for the script type, including version for V scripts and format."""
        parts = [self.type]
        if self.type == "V" and hasattr(self, "version"):
            parts.append(f"({self.version})")
        parts.append(self.format)
        return " ".join(parts)

    @staticmethod
    def get_script_name(file_path: Path) -> str:
        """Script name is the filename without any jinja extension"""
        if file_path.suffixes[-1].upper() == ".JINJA":
            return file_path.stem
        return file_path.name

    @classmethod
    def from_path(cls, file_path: Path, **kwargs) -> T:
        logger.debug("Script found", class_name=cls.__name__, file_path=file_path.as_posix())

        # script name is the filename without any jinja extension
        script_name = cls.get_script_name(file_path=file_path)
        name_parts = cls.pattern.search(file_path.name.strip())
        description = name_parts.group("description").replace("_", " ").capitalize()
        if len(name_parts.group("separator")) != 2:
            prefix = f"V{name_parts.group('version')}" if cls.type == "V" else cls.type

            raise ValueError(
                f'two underscores are required between "{prefix}" and the description: {file_path}\n{str(file_path)}'
            )
        # noinspection PyArgumentList
        return cls(name=script_name, file_path=file_path, description=description, **kwargs)


@dataclasses.dataclass(frozen=True)
class VersionedScript(Script):
    pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"^(V)(?P<version>([^_]|_(?!_))+)?(?P<separator>_{1,2})(?P<description>.+?)\.",
        re.IGNORECASE,
    )
    type: ClassVar[Literal["V"]] = "V"
    version_number_regex: ClassVar[str | None] = None
    version: str

    @classmethod
    def from_path(cls: T, file_path: Path, **kwargs) -> T:
        name_parts = cls.pattern.search(file_path.name.strip())

        version = name_parts.group("version")
        if version is None:
            raise ValueError(f"Versioned migrations must be prefixed with a version: {str(file_path)}")

        if cls.version_number_regex:
            if re.search(cls.version_number_regex, version, re.IGNORECASE) is None:
                raise ValueError(
                    f"change script version doesn't match the supplied regular expression: "
                    f"{cls.version_number_regex}\n{str(file_path)}"
                )

        return super().from_path(file_path=file_path, version=name_parts.group("version"))


@dataclasses.dataclass(frozen=True)
class RepeatableScript(Script):
    pattern: ClassVar[re.Pattern[str]] = re.compile(r"^(R)(?P<separator>_{1,2})(?P<description>.+?)\.", re.IGNORECASE)
    type: ClassVar[Literal["R"]] = "R"


@dataclasses.dataclass(frozen=True)
class AlwaysScript(Script):
    pattern: ClassVar[re.Pattern[str]] = re.compile(r"^(A)(?P<separator>_{1,2})(?P<description>.+?)\.", re.IGNORECASE)
    type: ClassVar[Literal["A"]] = "A"


# CLI Script classes for .cli.yml files
# These follow the same V/R/A versioning conventions but execute CLI commands instead of SQL


@dataclasses.dataclass(frozen=True)
class VersionedCLIScript(Script):
    """Versioned CLI migration script (.cli.yml)"""

    pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"^(V)(?P<version>([^_]|_(?!_))+)?(?P<separator>_{1,2})(?P<description>.+?)\.cli\.yml(\.jinja)?$",
        re.IGNORECASE,
    )
    type: ClassVar[Literal["V"]] = "V"
    format: ClassVar[Literal["CLI"]] = "CLI"
    version_number_regex: ClassVar[str | None] = None
    version: str

    @classmethod
    def from_path(cls: T, file_path: Path, **kwargs) -> T:
        name_parts = cls.pattern.search(file_path.name.strip())

        version = name_parts.group("version")
        if version is None:
            raise ValueError(f"Versioned CLI migrations must be prefixed with a version: {str(file_path)}")

        if cls.version_number_regex:
            if re.search(cls.version_number_regex, version, re.IGNORECASE) is None:
                raise ValueError(
                    f"CLI script version doesn't match the supplied regular expression: "
                    f"{cls.version_number_regex}\n{str(file_path)}"
                )

        return super().from_path(file_path=file_path, version=name_parts.group("version"))


@dataclasses.dataclass(frozen=True)
class RepeatableCLIScript(Script):
    """Repeatable CLI migration script (.cli.yml)"""

    pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"^(R)(?P<separator>_{1,2})(?P<description>.+?)\.cli\.yml(\.jinja)?$",
        re.IGNORECASE,
    )
    type: ClassVar[Literal["R"]] = "R"
    format: ClassVar[Literal["CLI"]] = "CLI"


@dataclasses.dataclass(frozen=True)
class AlwaysCLIScript(Script):
    """Always-run CLI migration script (.cli.yml)"""

    pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"^(A)(?P<separator>_{1,2})(?P<description>.+?)\.cli\.yml(\.jinja)?$",
        re.IGNORECASE,
    )
    type: ClassVar[Literal["A"]] = "A"
    format: ClassVar[Literal["CLI"]] = "CLI"


def cli_script_factory(file_path: Path) -> T | None:
    """Factory function to create CLI script objects from file paths."""
    if VersionedCLIScript.pattern.search(file_path.name.strip()) is not None:
        return VersionedCLIScript.from_path(file_path=file_path)

    elif RepeatableCLIScript.pattern.search(file_path.name.strip()) is not None:
        return RepeatableCLIScript.from_path(file_path=file_path)

    elif AlwaysCLIScript.pattern.search(file_path.name.strip()) is not None:
        return AlwaysCLIScript.from_path(file_path=file_path)

    return None


def script_factory(
    file_path: Path,
) -> T | None:
    if VersionedScript.pattern.search(file_path.name.strip()) is not None:
        return VersionedScript.from_path(file_path=file_path)

    elif RepeatableScript.pattern.search(file_path.name.strip()) is not None:
        return RepeatableScript.from_path(file_path=file_path)

    elif AlwaysScript.pattern.search(file_path.name.strip()) is not None:
        return AlwaysScript.from_path(file_path=file_path)

    logger.debug("ignoring non-change file", file_path=file_path.as_posix())


def get_all_scripts_recursively(root_directory: Path, version_number_regex: str | None = None):
    VersionedScript.version_number_regex = version_number_regex
    VersionedCLIScript.version_number_regex = version_number_regex

    all_files: dict[str, T] = {}
    all_versions = []
    # Walk the entire directory structure recursively
    # Match both SQL scripts (.sql, .sql.jinja) and CLI scripts (.cli.yml, .cli.yml.jinja)
    sql_pattern = re.compile(r"\.sql(\.jinja)?$", flags=re.IGNORECASE)
    cli_pattern = re.compile(r"\.cli\.yml(\.jinja)?$", flags=re.IGNORECASE)

    file_paths = root_directory.glob("**/*")
    for file_path in file_paths:
        if file_path.is_dir():
            continue

        # Determine script type and use appropriate factory
        script: T | None = None
        if cli_pattern.search(file_path.name.strip()):
            script = cli_script_factory(file_path=file_path)
        elif sql_pattern.search(file_path.name.strip()):
            script = script_factory(file_path=file_path)
        else:
            continue

        if script is None:
            continue

        # Throw an error if the script_name already exists
        if script.name.lower() in all_files:
            raise ValueError(
                f"The script name {script.name} exists more than once ("
                f"first_instance {str(all_files[script.name.lower()].file_path)}, "
                f"second instance {str(script.file_path)})"
            )

        all_files[script.name.lower()] = script

        # Throw an error if the same version exists more than once
        if script.type == "V":
            if script.version in all_versions:
                raise ValueError(
                    f"The script version {script.version} exists more than once "
                    f"(second instance {str(script.file_path)})"
                )
            all_versions.append(script.version)

    return all_files
