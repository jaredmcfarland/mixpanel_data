"""Shared CLI option definitions.

Provides reusable Annotated type aliases for common CLI options
to avoid duplication across commands.
"""

from __future__ import annotations

from typing import Annotated, Literal

import typer

# Output format type for formatting command output
OutputFormat = Literal["json", "jsonl", "table", "csv", "plain"]

# Reusable Annotated type for --format option
# Used by all commands that produce output
FormatOption = Annotated[
    OutputFormat,
    typer.Option(
        "--format",
        "-f",
        help="Output format: json, jsonl, table, csv, plain.",
    ),
]
