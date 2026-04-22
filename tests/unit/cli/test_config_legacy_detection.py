"""Unit tests for legacy v1/v2 config detection error message (T022).

The new v3 ``ConfigManager`` rejects legacy configs with a precise multi-line
error pointing at ``mp config convert``. This test pins the exact wording of
the error so the CLI / plugin can rely on its stability.

Once Phase 4 rewires the ``mp`` CLI to use the new ``ConfigManager`` directly,
invoking ANY ``mp`` command against a legacy config surfaces this same error —
this test will be extended at that point with subprocess assertions. For now
we assert the error from the library directly.

Reference: specs/042-auth-architecture-redesign/contracts/config-schema.md §1.4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mixpanel_data._internal.config_v3 import ConfigManager
from mixpanel_data.exceptions import ConfigError


_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "configs"


_EXPECTED_LINES = [
    "Legacy config schema detected at",
    "This version of mixpanel_data uses a single unified schema. Convert your config",
    "mp config convert",
    "After conversion, your old config will be archived as",
]


@pytest.mark.parametrize(
    "fixture",
    [
        "v1_simple.toml",
        "v1_multi.toml",
        "v1_with_oauth_orphan.toml",
        "v2_simple.toml",
        "v2_multi.toml",
        "v2_with_custom_header.toml",
    ],
)
def test_legacy_fixtures_surface_exact_error(
    fixture: str, tmp_path: Path
) -> None:
    """Each legacy fixture surfaces the canonical multi-line ConfigError message."""
    src = _FIXTURE_DIR / fixture
    dst = tmp_path / "config.toml"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    cm = ConfigManager(config_path=dst)
    with pytest.raises(ConfigError) as excinfo:
        cm.list_accounts()
    msg = str(excinfo.value)
    for expected in _EXPECTED_LINES:
        assert expected in msg, (
            f"Missing expected line {expected!r} in error message:\n{msg}"
        )
    # The path that triggered the error should appear verbatim.
    assert str(dst) in msg
