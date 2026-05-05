#!/usr/bin/env python3
"""Run the ``bookmark_schema`` Pydantic validator over a captured corpus.

Reads ``tests/fixtures/bookmark_corpus/{type}/*.json`` files produced by
``scripts/capture_bookmark_corpus.py`` and runs the new schema validator
against each. Reports any false-rejections so we can widen the schema
before tightening ``extra="forbid"`` further.

Output: a per-type summary plus a per-error-code distribution. Exits 0
when every bookmark validates cleanly, 1 when any rejections happen.

Usage:

```
uv run python scripts/validate_corpus.py [--corpus DIR] [--verbose]
```
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from mixpanel_data._internal.bookmark_schema import (
    get_root_model_for_bookmark_type,
    validate_with_pydantic,
)


def _validate_one_file(path: Path) -> tuple[str, list[Any]]:
    """Validate one corpus file and return ``(bookmark_type, errors)``."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    bookmark_type = raw.get("bookmark_type", path.parent.name)
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        return bookmark_type, []
    root = get_root_model_for_bookmark_type(bookmark_type)
    if root is None:
        return bookmark_type, []
    errors = validate_with_pydantic(root, params)
    return bookmark_type, errors


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate a captured bookmark corpus against the new "
            "bookmark_schema models. Surfaces false-rejections."
        )
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("tests/fixtures/bookmark_corpus"),
        help="Corpus directory (default: tests/fixtures/bookmark_corpus).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every individual error (not just the summary).",
    )
    args = parser.parse_args()

    if not args.corpus.exists():
        print(f"Corpus directory not found: {args.corpus}")
        print(
            "Run scripts/capture_bookmark_corpus.py first to populate it."
        )
        return 1

    files = sorted(args.corpus.glob("*/*.json"))
    if not files:
        print(f"No corpus files found under {args.corpus}/*/*.json")
        return 1

    print(f"Validating {len(files)} bookmark fixtures from {args.corpus}...")
    print()

    by_type_total: Counter[str] = Counter()
    by_type_errored: Counter[str] = Counter()
    code_counts: Counter[str] = Counter()
    rejection_paths: Counter[str] = Counter()

    for path in files:
        bookmark_type, errors = _validate_one_file(path)
        by_type_total[bookmark_type] += 1
        if errors:
            by_type_errored[bookmark_type] += 1
            for e in errors:
                code_counts[e.code] += 1
                rejection_paths[e.path] += 1
            if args.verbose:
                print(f"  {path.relative_to(args.corpus)}: {len(errors)} errors")
                for e in errors[:5]:
                    print(f"    {e.code}: {e.path}: {e.message[:80]}")

    print("Per-type summary:")
    for bt in sorted(by_type_total):
        total = by_type_total[bt]
        errored = by_type_errored[bt]
        pct = 100.0 * (total - errored) / total if total else 0.0
        print(f"  {bt:>10}: {total - errored} / {total} pass ({pct:.1f}%)")

    if code_counts:
        print()
        print("Error codes (top 10):")
        for code, count in code_counts.most_common(10):
            print(f"  {code:<30}: {count}")

        print()
        print("Most-rejected paths (top 10):")
        for path, count in rejection_paths.most_common(10):
            print(f"  {count:>4} × {path}")

    has_errors = sum(by_type_errored.values()) > 0
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
