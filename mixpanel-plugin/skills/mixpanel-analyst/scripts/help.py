#!/usr/bin/env python3
"""Programmatic API documentation lookup for mixpanel_data.

Usage:
    python help.py Workspace                    # List all Workspace methods
    python help.py Workspace.segmentation       # Method signature + docstring
    python help.py SegmentationResult           # Type/class documentation
    python help.py FeatureFlagStatus            # Enum members + values
    python help.py types                        # List all public types
    python help.py exceptions                   # List all exceptions
"""

import contextlib
import dataclasses
import enum
import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

try:
    from pydantic_core import PydanticUndefined
except ImportError:
    PydanticUndefined = None  # type: ignore[assignment,misc]


def get_obj(path: str) -> Any:
    """Navigate a dotted path from mixpanel_data to find the target object."""
    mod = importlib.import_module("mixpanel_data")
    parts = path.split(".")
    obj: Any = mod
    for part in parts:
        obj = getattr(obj, part)
    return obj


def format_type(annotation: Any) -> str:
    """Format a type annotation for clean display.

    Args:
        annotation: A type annotation (class, generic, union, etc.).

    Returns:
        Human-readable type string with noise removed.
    """
    if annotation is None or annotation is type(None):
        return "None"
    if hasattr(annotation, "__name__") and not hasattr(annotation, "__args__"):
        return annotation.__name__
    s = str(annotation)
    s = s.replace("typing.", "").replace("typing_extensions.", "")
    s = s.replace("<class '", "").replace("'>", "")
    s = s.replace("NoneType", "None")
    return s


def _enum_values_inline(annotation: Any) -> str:
    """Return inline enum member names if annotation contains an Enum type.

    Args:
        annotation: A type annotation to inspect.

    Returns:
        String like ' [ENABLED | DISABLED | ARCHIVED]' or empty string.
    """
    candidates: list[type] = []
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        candidates.append(annotation)
    args = getattr(annotation, "__args__", None)
    if args:
        for arg in args:
            if isinstance(arg, type) and issubclass(arg, enum.Enum):
                candidates.append(arg)
    if not candidates:
        return ""
    all_names: list[str] = []
    for cls in candidates:
        all_names.extend(m.name for m in cls)
    return f" [{' | '.join(all_names)}]"


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
                annotation = f": {format_type(param.annotation)}"
            default = ""
            if param.default != inspect.Parameter.empty:
                default = f" = {param.default!r}"
            params.append(f"    {pname}{annotation}{default}")

        ret = ""
        if sig.return_annotation != inspect.Signature.empty:
            ret = f" -> {format_type(sig.return_annotation)}"

        param_str = ",\n".join(params)
        if params:
            return f"{name}(\n{param_str}\n){ret}"
        return f"{name}(){ret}"
    except (ValueError, TypeError):
        return f"{name}(...)"


def show_enum(obj: type, name: str) -> None:
    """Display enum members with their values.

    Args:
        obj: An Enum subclass.
        name: Display name for the enum.
    """
    members = list(obj)  # type: ignore[arg-type]
    print(f"# {name} \u2014 {len(members)} members\n")
    max_name_len = max((len(m.name) for m in members), default=0)
    for member in members:
        print(f"  {member.name:<{max_name_len}}  = {member.value!r}")
    doc = inspect.getdoc(obj)
    if doc:
        print(f"\n{doc}")


def list_members(obj: Any, name: str) -> None:
    """List public methods and properties of an object."""
    if isinstance(obj, type) and issubclass(obj, enum.Enum):
        show_enum(obj, name)
        return

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

    print(f"# {name} \u2014 {len(members)} public members\n")
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
        if (
            isinstance(obj, type)
            and name != "Workspace"
            and not issubclass(obj, Exception)
        ):
            doc = inspect.getdoc(obj) or ""
            first_line = doc.split("\n")[0] if doc else ""
            types_list.append((name, first_line))

    print(f"# mixpanel_data \u2014 {len(types_list)} public types\n")
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

    print(f"# mixpanel_data \u2014 {len(excs)} exception types\n")
    for name, desc in excs:
        print(f"  {name:35s} {desc}")


def show_fields(obj: type, indent: str = "") -> None:
    """Show fields for dataclasses or Pydantic models.

    Args:
        obj: A dataclass or Pydantic BaseModel class.
        indent: Prefix for indentation.
    """
    if hasattr(obj, "__dataclass_fields__"):
        print(f"\n{indent}Fields:")
        for fname, field in obj.__dataclass_fields__.items():
            ftype = format_type(field.type) if hasattr(field, "type") else "?"
            default = ""
            try:
                if field.default is not dataclasses.MISSING:
                    default = f" = {field.default!r}"
                elif field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                    factory_name = getattr(
                        field.default_factory, "__name__", repr(field.default_factory)
                    )
                    default = f" = <factory {factory_name}>"
            except Exception:
                pass
            print(f"{indent}  {fname}: {ftype}{default}")
    elif hasattr(obj, "model_fields"):
        # Resolve alias generator from model config
        config = getattr(obj, "model_config", {})
        alias_gen = config.get("alias_generator")

        print(f"\n{indent}Fields:")
        for fname, finfo in obj.model_fields.items():
            type_str = format_type(finfo.annotation)
            enum_inline = _enum_values_inline(finfo.annotation)

            # Default value handling (fix PydanticUndefined leak)
            if finfo.is_required():
                default = " (required)"
            elif PydanticUndefined is not None and finfo.default is PydanticUndefined:
                if finfo.default_factory is not None:
                    factory_name = getattr(finfo.default_factory, "__name__", "factory")
                    default = f" = <factory {factory_name}>"
                else:
                    default = " (required)"
            elif finfo.default is None:
                default = ""
            else:
                default = f" = {finfo.default!r}"

            # Field constraints from metadata
            constraints = ""
            if finfo.metadata:
                constraint_parts: list[str] = []
                for meta in finfo.metadata:
                    for attr in (
                        "max_length",
                        "min_length",
                        "ge",
                        "le",
                        "gt",
                        "lt",
                        "multiple_of",
                        "pattern",
                    ):
                        val = getattr(meta, attr, None)
                        if val is not None:
                            constraint_parts.append(f"{attr}={val}")
                if constraint_parts:
                    constraints = f" ({', '.join(constraint_parts)})"

            # Alias resolution
            alias_info = ""
            resolved_alias = finfo.alias
            if resolved_alias is None and alias_gen and callable(alias_gen):
                with contextlib.suppress(Exception):
                    resolved_alias = alias_gen(fname)
            if resolved_alias and resolved_alias != fname:
                alias_info = f' (json: "{resolved_alias}")'

            print(
                f"{indent}  {fname}: "
                f"{type_str}{enum_inline}{default}{constraints}{alias_info}"
            )


def show_model_config(obj: type) -> None:
    """Show non-default Pydantic model config values.

    Args:
        obj: A Pydantic BaseModel subclass.
    """
    config = getattr(obj, "model_config", None)
    if not config:
        return
    defaults = {
        "frozen": False,
        "extra": "ignore",
        "populate_by_name": False,
    }
    parts: list[str] = []
    for key, default_val in defaults.items():
        val = config.get(key)
        if val is not None and val != default_val:
            parts.append(f"{key}={val!r}")
    ag = config.get("alias_generator")
    if ag is not None:
        gen_name = getattr(ag, "__name__", str(ag))
        parts.append(f"alias_generator={gen_name}")
    if parts:
        print(f"  Config: {', '.join(parts)}")


def show_related(type_name: str) -> None:
    """Show Workspace methods that reference the given type.

    Args:
        type_name: Simple class name to search for in method signatures.
    """
    mod = importlib.import_module("mixpanel_data")
    ws_cls = getattr(mod, "Workspace", None)
    if ws_cls is None:
        return

    matches: list[str] = []
    for attr_name in sorted(dir(ws_cls)):
        if attr_name.startswith("_"):
            continue
        attr = getattr(ws_cls, attr_name, None)
        if not callable(attr) or isinstance(attr, property):
            continue
        try:
            sig = inspect.signature(attr)
        except (ValueError, TypeError):
            continue

        if type_name not in str(sig):
            continue

        ret = ""
        if sig.return_annotation != inspect.Signature.empty:
            ret = f" -> {format_type(sig.return_annotation)}"
        param_parts: list[str] = []
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            if param.annotation != inspect.Parameter.empty:
                param_parts.append(f"{pname}: {format_type(param.annotation)}")
            else:
                param_parts.append(pname)
        params_str = ", ".join(param_parts)
        matches.append(f"  {attr_name}({params_str}){ret}")

    if matches:
        print(f"\nUsed by Workspace ({len(matches)} methods):")
        for m in matches:
            print(m)


_BOOKMARK_RELATED = frozenset(
    {
        "query_saved_report",
        "query_flows",
        "SavedReportResult",
        "SavedReportType",
        "FlowsResult",
    }
)


def _maybe_show_bookmark_hint(query: str) -> None:
    """Print a reference hint if the query relates to bookmarks.

    Args:
        query: The user's help query string.
    """
    parts = query.replace(".", " ").split()
    if "bookmark" not in query.lower() and not (set(parts) & _BOOKMARK_RELATED):
        return
    ref = Path(__file__).resolve().parent.parent / "references" / "bookmark-params.md"
    if not ref.is_file():
        return
    print(
        "\n---\n"
        "Tip: For bookmark params JSON schema, "
        "read references/bookmark-params.md "
        "(SQL-to-JSON query translation guide)"
    )


def show_detail(obj: Any, path: str) -> None:
    """Show detailed documentation for a specific object."""
    if isinstance(obj, type) and issubclass(obj, enum.Enum):
        show_enum(obj, path)
        show_related(path.split(".")[-1])
        return

    if isinstance(obj, type):
        print(f"class {path}")
        bases = [b.__name__ for b in obj.__mro__[1:] if b.__name__ != "object"]
        if bases:
            arrow = " \u2192 "
            print(f"  Inherits: {arrow.join(bases)}")
        if hasattr(obj, "model_config"):
            show_model_config(obj)
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

    if isinstance(obj, type) and path.split(".")[-1] != "Workspace":
        show_related(path.split(".")[-1])


def main() -> None:
    """Entry point for the help script."""
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
            if isinstance(obj, type) and issubclass(obj, enum.Enum):
                show_enum(obj, query)
                show_related(query)
            elif isinstance(obj, type):
                if hasattr(obj, "model_fields") or hasattr(obj, "__dataclass_fields__"):
                    show_detail(obj, query)
                else:
                    list_members(obj, query)
            else:
                show_detail(obj, query)
        except AttributeError:
            print(f"Error: '{query}' not found in mixpanel_data")
            print(
                "Try: Workspace, types, exceptions, or a dotted path"
                " like Workspace.segmentation"
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

    if query not in ("types", "exceptions"):
        _maybe_show_bookmark_hint(query)


if __name__ == "__main__":
    main()
