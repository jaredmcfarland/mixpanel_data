"""
mixpanel_data - Python library for working with Mixpanel analytics data.

Designed for AI coding agents. Fetch data once into a local DuckDB database,
then query it repeatedly with SQL.
"""

from mixpanel_data.exceptions import (
    AccountExistsError,
    AccountNotFoundError,
    APIError,
    AuthenticationError,
    ConfigError,
    JQLSyntaxError,
    MixpanelDataError,
    QueryError,
    RateLimitError,
    ServerError,
    TableExistsError,
    TableNotFoundError,
)
from mixpanel_data.types import (
    CohortInfo,
    EventCountsResult,
    FetchResult,
    FunnelInfo,
    FunnelResult,
    FunnelStep,
    JQLResult,
    PropertyCountsResult,
    RetentionResult,
    SavedCohort,
    SegmentationResult,
    TopEvent,
)

__version__ = "0.1.0"

__all__ = [
    # Exceptions
    "MixpanelDataError",
    "APIError",
    "ConfigError",
    "AccountNotFoundError",
    "AccountExistsError",
    "AuthenticationError",
    "RateLimitError",
    "QueryError",
    "JQLSyntaxError",
    "ServerError",
    "TableExistsError",
    "TableNotFoundError",
    # Result types
    "FetchResult",
    "SegmentationResult",
    "FunnelResult",
    "FunnelStep",
    "RetentionResult",
    "CohortInfo",
    "JQLResult",
    # Discovery types
    "FunnelInfo",
    "SavedCohort",
    "TopEvent",
    "EventCountsResult",
    "PropertyCountsResult",
]
