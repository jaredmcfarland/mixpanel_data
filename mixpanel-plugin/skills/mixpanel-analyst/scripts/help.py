#!/usr/bin/env python3
"""Programmatic API documentation lookup for mixpanel_data.

Usage:
    python help.py Workspace                    # List all Workspace methods
    python help.py Workspace.segmentation       # Method signature + docstring
    python help.py SegmentationResult           # Type/class documentation
    python help.py types                        # List all public types
    python help.py exceptions                   # List all exceptions
"""

import dataclasses
import importlib
import inspect
import sys
from typing import Any


def get_obj(path: str) -> Any:
    """Navigate a dotted path from mixpanel_data to find the target object."""
    mod = importlib.import_module("mixpanel_data")
    parts = path.split(".")
    obj: Any = mod
    for part in parts:
        obj = getattr(obj, part)
    return obj


def format_signature(obj: Any, name: str) -> str:
    """Format a callable's full signature with type annotations."""
    try:
        sig = inspect.signature(obj)
        params = []
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            annotation = ""
            if param.annotation != inspect.Parameter.empty:
                ann = param.annotation
                annotation = (
                    f": {ann.__name__}" if hasattr(ann, "__name__") else f": {ann}"
                )
            default = ""
            if param.default != inspect.Parameter.empty:
                default = f" = {param.default!r}"
            params.append(f"    {pname}{annotation}{default}")

        ret = ""
        if sig.return_annotation != inspect.Signature.empty:
            ra = sig.return_annotation
            ret = f" -> {ra.__name__}" if hasattr(ra, "__name__") else f" -> {ra}"

        param_str = ",\n".join(params)
        if params:
            return f"{name}(\n{param_str}\n){ret}"
        return f"{name}(){ret}"
    except (ValueError, TypeError):
        return f"{name}(...)"


def list_members(obj: Any, name: str) -> None:
    """List public methods and properties of an object."""
    members: list[tuple[str, str]] = []
    for attr_name in sorted(dir(obj)):
        if attr_name.startswith("_"):
            continue
        try:
            attr = getattr(obj, attr_name, None)
        except Exception:
            continue

        if attr is None:
            continue

        doc = inspect.getdoc(attr) or ""
        first_line = doc.split("\n")[0] if doc else "(no description)"

        if isinstance(attr, property):
            members.append((attr_name, f"[property] {first_line}"))
        elif callable(attr):
            members.append((attr_name, first_line))

    print(f"# {name} — {len(members)} public members\n")
    for mname, desc in members:
        print(f"  {mname:42s} {desc}")


def list_types() -> None:
    """List all public types exported by mixpanel_data."""
    mod = importlib.import_module("mixpanel_data")
    types_list: list[tuple[str, str]] = []
    for name in sorted(dir(mod)):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name)
        if isinstance(obj, type) and name != "Workspace":
            doc = inspect.getdoc(obj) or ""
            first_line = doc.split("\n")[0] if doc else ""
            types_list.append((name, first_line))

    print(f"# mixpanel_data — {len(types_list)} public types\n")
    for name, desc in types_list:
        print(f"  {name:45s} {desc}")


def list_exceptions() -> None:
    """List all exception types from mixpanel_data."""
    mod = importlib.import_module("mixpanel_data")
    excs: list[tuple[str, str]] = []
    for name in sorted(dir(mod)):
        obj = getattr(mod, name)
        if isinstance(obj, type) and issubclass(obj, Exception):
            doc = inspect.getdoc(obj) or ""
            first_line = doc.split("\n")[0] if doc else ""
            excs.append((name, first_line))

    print(f"# mixpanel_data — {len(excs)} exception types\n")
    for name, desc in excs:
        print(f"  {name:35s} {desc}")


def show_fields(obj: type, indent: str = "") -> None:
    """Show fields for dataclasses or Pydantic models."""
    if hasattr(obj, "__dataclass_fields__"):
        print(f"\n{indent}Fields:")
        for fname, field in obj.__dataclass_fields__.items():
            ftype = field.type if hasattr(field, "type") else "?"
            default = ""
            if field.default is not field.default_factory:  # type: ignore[attr-defined]
                try:
                    if field.default is not dataclasses.MISSING:  # type: ignore[name-defined]
                        default = f" = {field.default!r}"
                except Exception:
                    pass
            print(f"{indent}  {fname}: {ftype}{default}")
    elif hasattr(obj, "model_fields"):
        print(f"\n{indent}Fields:")
        for fname, finfo in obj.model_fields.items():
            required = " (required)" if finfo.is_required() else ""
            default = ""
            if not finfo.is_required() and finfo.default is not None:
                default = f" = {finfo.default!r}"
            print(f"{indent}  {fname}: {finfo.annotation}{required}{default}")


def show_detail(obj: Any, path: str) -> None:
    """Show detailed documentation for a specific object."""
    if isinstance(obj, type):
        print(f"class {path}")
        # Show base classes
        bases = [b.__name__ for b in obj.__mro__[1:] if b.__name__ != "object"]
        if bases:
            print(f"  Inherits: {' → '.join(bases)}")
        show_fields(obj)
    elif callable(obj):
        print(format_signature(obj, path))
    else:
        print(f"{path} = {obj!r}")

    doc = inspect.getdoc(obj)
    if doc:
        print(f"\n{doc}")
    else:
        print("\n(no docstring)")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    query = sys.argv[1]

    try:
        importlib.import_module("mixpanel_data")
    except ImportError:
        print("Error: mixpanel_data is not installed.")
        print("Run /mixpanel-data:setup to install it.")
        sys.exit(1)

    if query == "types":
        list_types()
    elif query == "exceptions":
        list_exceptions()
    elif "." not in query:
        try:
            obj = get_obj(query)
            if isinstance(obj, type):
                # For types with fields, show detail; for Workspace, list methods
                if hasattr(obj, "model_fields") or hasattr(obj, "__dataclass_fields__"):
                    show_detail(obj, query)
                else:
                    list_members(obj, query)
            else:
                show_detail(obj, query)
        except AttributeError:
            print(f"Error: '{query}' not found in mixpanel_data")
            print(
                "Try: Workspace, types, exceptions, or a dotted path like Workspace.segmentation"
            )
            sys.exit(1)
    else:
        try:
            obj = get_obj(query)
            show_detail(obj, query)
        except AttributeError as e:
            print(f"Error: {e}")
            parts = query.rsplit(".", 1)
            if len(parts) == 2:
                try:
                    parent = get_obj(parts[0])
                    print(f"\nAvailable on {parts[0]}:")
                    list_members(parent, parts[0])
                except AttributeError:
                    pass
            sys.exit(1)


if __name__ == "__main__":
    main()
