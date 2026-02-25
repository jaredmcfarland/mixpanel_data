"""Helper functions for Operational Analytics Loop workflows.

Utility functions shared across workflow tools.
"""

import hashlib


def generate_anomaly_id(
    event: str,
    anomaly_type: str,
    date: str,
    dimension: str | None = None,
    dimension_value: str | None = None,
) -> str:
    """Generate deterministic anomaly ID for referencing across tools.

    Creates a content-based hash ID that remains stable across scans
    for the same anomaly. Format: {event}_{type}_{date}_{hash8}

    Args:
        event: Event name (e.g., "signup").
        anomaly_type: Type of anomaly ("drop", "spike", "trend_change", "segment_shift").
        date: Detection date in YYYY-MM-DD format.
        dimension: Optional property dimension (e.g., "platform").
        dimension_value: Optional dimension value (e.g., "iOS").

    Returns:
        Deterministic anomaly ID.

    Example:
        ```python
        anomaly_id = generate_anomaly_id(
            event="signup",
            anomaly_type="drop",
            date="2025-01-15",
        )
        # "signup_drop_2025-01-15_a3f2b1c9"

        anomaly_id = generate_anomaly_id(
            event="login",
            anomaly_type="segment_shift",
            date="2025-01-10",
            dimension="country",
            dimension_value="US",
        )
        # "login_segment_shift_2025-01-10_country_US_b2c1d3e4"
        ```
    """
    components = [event, anomaly_type, date]
    if dimension and dimension_value:
        components.extend([dimension, dimension_value])

    content = "|".join(components)
    hash_digest = hashlib.sha256(content.encode()).hexdigest()[:8]

    base = f"{event}_{anomaly_type}_{date}"
    if dimension and dimension_value:
        base = f"{base}_{dimension}_{dimension_value}"

    return f"{base}_{hash_digest}"
