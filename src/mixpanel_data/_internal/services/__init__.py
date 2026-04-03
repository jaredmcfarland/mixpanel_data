"""Service layer for mixpanel_data.

This package contains high-level service classes that orchestrate
operations using the lower-level API client.
"""

from mixpanel_data._internal.services.discovery import DiscoveryService
from mixpanel_data._internal.services.live_query import LiveQueryService

__all__ = ["DiscoveryService", "LiveQueryService"]
