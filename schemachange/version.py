"""
Version comparison utilities for schemachange.

These functions provide alphanumeric version comparison that correctly handles
semantic versioning, timestamp-based versions, and other common versioning schemes.
"""

from __future__ import annotations

import re


def alphanum_convert(text: str):
    """Convert a string to int if it's numeric, otherwise lowercase it."""
    if text.isdigit():
        return int(text)
    return text.lower()


def get_alphanum_key(key: str | int | None) -> list:
    """
    Return a list containing the parts of the key (split by number parts).

    Each number is converted to an integer and string parts are left as strings.
    This enables correct sorting in Python when the lists are compared.

    Example:
        get_alphanum_key('1.2.2') results in ['', 1, '.', 2, '.', 2, '']
        get_alphanum_key('1.0.10') results in ['', 1, '.', 0, '.', 10, '']

    This ensures that '1.0.10' > '1.0.2' (correct) rather than '1.0.10' < '1.0.2' (string comparison).
    """
    if key == "" or key is None:
        return []
    alphanum_key = [alphanum_convert(c) for c in re.split("([0-9]+)", str(key))]
    return alphanum_key


def sorted_alphanumeric(data):
    """Sort a list of strings using alphanumeric comparison."""
    return sorted(data, key=get_alphanum_key)


def max_alphanumeric(versions: list[str | int | None]) -> str | int | None:
    """
    Find the maximum version from a list using alphanumeric comparison.

    Args:
        versions: List of version strings/numbers (may contain None values)

    Returns:
        The maximum version, or None if the list is empty or contains only None values
    """
    # Filter out None and empty values
    valid_versions = [v for v in versions if v is not None and v != ""]
    if not valid_versions:
        return None
    return max(valid_versions, key=get_alphanum_key)
