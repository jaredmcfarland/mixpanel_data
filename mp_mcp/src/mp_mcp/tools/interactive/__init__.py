"""Interactive tools for Mixpanel analytics with user elicitation.

This package contains tools that use ctx.elicit() for user interaction:

- guided: guided_analysis - Multi-step guided analysis workflow

These tools use ctx.elicit() to request user input mid-execution,
enabling interactive workflows and confirmation dialogs.
"""

# Import tool modules to register them with the server
# These imports happen when this package is imported by server.py
from mp_mcp.tools.interactive import guided  # noqa: F401

__all__ = [
    "guided",
]
