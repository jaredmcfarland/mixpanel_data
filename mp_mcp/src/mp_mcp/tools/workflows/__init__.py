"""Workflow (Tier 3) tools for Operational Analytics Loop.

This package contains high-level orchestration tools that compose multiple
primitives into a cohesive workflow for daily/weekly analytical rituals:

- context: Gather project landscape for analytics workflow
- health: Generate KPI dashboard with period comparison
- scan: Detect anomalies using statistical methods
- investigate: Root cause analysis for detected anomalies
- report: Synthesize findings into actionable reports

These tools follow the established FastMCP patterns with @mcp.tool + @handle_errors
decorators and rate-limited workspace access.

Example:
    Full workflow:
    1. context() - Prime context with project landscape
    2. health() - Generate KPI dashboard
    3. scan() - Detect anomalies
    4. investigate(anomaly_id="...") - Root cause analysis
    5. report(investigation=...) - Generate report
"""

# Import helper function first to avoid circular imports
# Import tool modules to register them with the server
# These imports happen when this package is imported by server.py
from mp_mcp.tools.workflows import (  # noqa: F401
    context,
    health,
    investigate,
    report,
    scan,
)
from mp_mcp.tools.workflows.helpers import generate_anomaly_id

__all__ = [
    "context",
    "health",
    "scan",
    "investigate",
    "report",
    "generate_anomaly_id",
]
