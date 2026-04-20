"""Property-based tests for config v2.

Tests cover:
- T082: Migration round-trip (v1 projects accessible after migration)
- T113: Config v2 round-trip (write -> read = identity)

Uses Hypothesis with profiles configured in tests/conftest.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import tomli_w
from hypothesis import given, settings
from hypothesis import strategies as st

from mixpanel_data._internal.auth_credential import RegionType
from mixpanel_data._internal.config import AuthMethod, ConfigManager, Credentials

# ── Strategies ────────────────────────────────────────────────────────

# Strategy for valid Mixpanel region strings
region_st = st.sampled_from(["us", "eu", "in"])

# Strategy for non-empty alphanumeric identifiers (safe for TOML keys)
identifier_st = st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)

# Strategy for project IDs (numeric strings)
project_id_st = st.from_regex(r"[1-9][0-9]{0,9}", fullmatch=True)

# Strategy for service account usernames
username_st = st.from_regex(r"[a-z][a-z0-9_.]{2,29}", fullmatch=True)

# Strategy for secrets (non-empty ASCII strings)
secret_st = st.from_regex(r"[a-zA-Z0-9]{8,32}", fullmatch=True)


# Strategy for a single v1 account entry
@st.composite
def v1_account_st(
    draw: st.DrawFn,
) -> tuple[str, dict[str, str]]:
    """Generate a single v1 account entry (name, data dict).

    Args:
        draw: Hypothesis draw function.

    Returns:
        Tuple of (account_name, account_data_dict).
    """
    name = draw(identifier_st)
    data = {
        "username": draw(username_st),
        "secret": draw(secret_st),
        "project_id": draw(project_id_st),
        "region": draw(region_st),
    }
    return name, data


# Strategy for a complete v1 config with 1-5 accounts
@st.composite
def v1_config_st(
    draw: st.DrawFn,
) -> dict[str, object]:
    """Generate a valid v1 config with 1-5 unique accounts.

    Ensures account names are unique and a valid default is set.

    Args:
        draw: Hypothesis draw function.

    Returns:
        A v1 config dictionary.
    """
    # Generate 1-5 unique accounts
    num_accounts = draw(st.integers(min_value=1, max_value=5))
    accounts: dict[str, dict[str, str]] = {}
    names_used: set[str] = set()

    for _ in range(num_accounts):
        # Keep generating until we get a unique name
        name = draw(identifier_st.filter(lambda n: n not in names_used))
        names_used.add(name)
        data = {
            "username": draw(username_st),
            "secret": draw(secret_st),
            "project_id": draw(project_id_st),
            "region": draw(region_st),
        }
        accounts[name] = data

    account_names = list(accounts.keys())
    default = draw(st.sampled_from(account_names))

    config: dict[str, object] = {
        "default": default,
        "accounts": accounts,
    }
    return config


# ── T082: Migration round-trip property ──────────────────────────────


class TestMigrationRoundTrip:
    """T082: For any valid v1 config, after migration all project_ids are accessible."""

    @given(v1_config=v1_config_st())
    @settings(max_examples=50, suppress_health_check=[])
    def test_all_project_ids_accessible_after_migration(
        self, v1_config: dict[str, object]
    ) -> None:
        """After migrating any valid v1 config, every original project_id is in aliases.

        Args:
            v1_config: A randomly generated v1 config.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with config_path.open("wb") as f:
                tomli_w.dump(v1_config, f)

            cm = ConfigManager(config_path=config_path)

            # Collect original project_ids
            accounts = v1_config.get("accounts", {})
            assert isinstance(accounts, dict)
            original_project_ids = {
                data["project_id"]
                for data in accounts.values()
                if isinstance(data, dict)
            }

            # Migrate
            result = cm.migrate_v1_to_v2()

            # Verify all original project_ids are accessible via aliases
            aliases = cm.list_project_aliases()
            alias_project_ids = {a.project_id for a in aliases}

            assert original_project_ids <= alias_project_ids, (
                f"Missing project_ids after migration: "
                f"{original_project_ids - alias_project_ids}"
            )

            # Verify credential count is <= account count (deduplication)
            assert result.credentials_created <= len(accounts)

            # Verify alias count matches account count
            assert result.aliases_created == len(accounts)


# ── T113: Config v2 round-trip property ──────────────────────────────


class TestConfigV2RoundTrip:
    """T113: Write -> read identity for v2 config operations."""

    @given(
        name=identifier_st,
        username=username_st,
        secret=secret_st,
        region=region_st,
    )
    @settings(max_examples=50, suppress_health_check=[])
    def test_add_credential_round_trip(
        self,
        name: str,
        username: str,
        secret: str,
        region: str,
    ) -> None:
        """Adding a credential and listing it returns the same data.

        Args:
            name: Credential name.
            username: Service account username.
            secret: Service account secret.
            region: Data residency region.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            cm = ConfigManager(config_path=config_path)

            cm.add_credential(
                name=name,
                type="service_account",
                username=username,
                secret=secret,
                region=region,
            )

            creds = cm.list_credentials()
            assert len(creds) == 1
            assert creds[0].name == name
            assert creds[0].type == "service_account"
            assert creds[0].region == region

    @given(
        alias_name=identifier_st,
        project_id=project_id_st,
    )
    @settings(max_examples=50, suppress_health_check=[])
    def test_add_project_alias_round_trip(
        self,
        alias_name: str,
        project_id: str,
    ) -> None:
        """Adding a project alias and listing returns the same data.

        Args:
            alias_name: Alias name.
            project_id: Project ID.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            cm = ConfigManager(config_path=config_path)

            cm.add_project_alias(
                name=alias_name,
                project_id=project_id,
            )

            aliases = cm.list_project_aliases()
            assert len(aliases) == 1
            assert aliases[0].name == alias_name
            assert aliases[0].project_id == project_id


# ── Credentials.from_oauth_token ──────────────────────────────────────


# Strategy for OAuth bearer tokens — printable ASCII covering RFC 6750
# token68 syntax (alphanumerics + - . _ ~ + / =). The `[A-Za-z._\-~+/=]`
# prefix forces a non-digit first character, which both matches realistic
# token shapes and prevents accidental substring collisions with the
# all-digit ``project_id_st`` strategy in redaction assertions.
oauth_token_st = st.from_regex(
    r"[A-Za-z._\-~+/=][A-Za-z0-9._\-~+/=]{7,63}", fullmatch=True
)

# Whitespace strategy for edge-stripping property — ASCII whitespace only,
# avoiding control chars that would correctly be rejected by the validator.
edge_ws_st = st.text(alphabet=" \t\n\r", min_size=0, max_size=4)

# Strategy for control characters (0x00-0x1F + 0x7F). Used to assert
# rejection — any token with one of these bytes embedded must raise.
control_char_st = st.sampled_from([chr(c) for c in list(range(0x20)) + [0x7F]])


class TestFromOAuthTokenProperties:
    """Property-based tests for ``Credentials.from_oauth_token``."""

    @given(token=oauth_token_st, project_id=project_id_st, region=region_st)
    @settings(max_examples=50)
    def test_auth_header_is_bearer_token(
        self,
        token: str,
        project_id: str,
        region: str,
    ) -> None:
        """For any valid token, ``auth_header`` must equal ``f"Bearer {token}"``.

        Args:
            token: A non-empty bearer token.
            project_id: A valid Mixpanel project ID.
            region: A valid Mixpanel region.
        """
        creds = Credentials.from_oauth_token(
            token=token,
            project_id=project_id,
            region=cast(RegionType, region),
        )
        assert creds.auth_header() == f"Bearer {token}"
        assert creds.auth_method == AuthMethod.oauth

    @given(token=oauth_token_st, project_id=project_id_st, region=region_st)
    @settings(max_examples=50)
    def test_token_redacted_in_repr(
        self,
        token: str,
        project_id: str,
        region: str,
    ) -> None:
        """The token must never appear in ``repr``/``str`` output.

        Args:
            token: A non-empty bearer token.
            project_id: A valid Mixpanel project ID.
            region: A valid Mixpanel region.
        """
        creds = Credentials.from_oauth_token(
            token=token,
            project_id=project_id,
            region=cast(RegionType, region),
        )
        assert token not in repr(creds)
        assert token not in str(creds)

    @given(
        leading_ws=edge_ws_st,
        token=oauth_token_st,
        trailing_ws=edge_ws_st,
        project_id=project_id_st,
        region=region_st,
    )
    @settings(max_examples=50)
    def test_edge_whitespace_is_stripped(
        self,
        leading_ws: str,
        token: str,
        trailing_ws: str,
        project_id: str,
        region: str,
    ) -> None:
        """Surrounding whitespace must be stripped before the Bearer header.

        Args:
            leading_ws: Whitespace prepended to the token.
            token: Core bearer token.
            trailing_ws: Whitespace appended to the token.
            project_id: A valid Mixpanel project ID.
            region: A valid Mixpanel region.
        """
        padded = f"{leading_ws}{token}{trailing_ws}"
        creds = Credentials.from_oauth_token(
            token=padded,
            project_id=project_id,
            region=cast(RegionType, region),
        )
        assert creds.auth_header() == f"Bearer {token}"

    @given(
        prefix=oauth_token_st,
        bad_char=control_char_st,
        suffix=oauth_token_st,
        project_id=project_id_st,
        region=region_st,
    )
    @settings(max_examples=50)
    def test_control_char_token_rejected(
        self,
        prefix: str,
        bad_char: str,
        suffix: str,
        project_id: str,
        region: str,
    ) -> None:
        """Any embedded control character must be rejected with ValueError.

        Whitespace-only embedded control chars (``\\n``, ``\\t``, ``\\r``)
        are stripped at the edges by ``from_oauth_token`` but survive in
        the middle of a token, where they would corrupt the
        ``Authorization: Bearer`` header.

        Args:
            prefix: Token characters before the control char.
            bad_char: A single control character (0x00-0x1F or 0x7F).
            suffix: Token characters after the control char.
            project_id: A valid Mixpanel project ID.
            region: A valid Mixpanel region.
        """
        token = f"{prefix}{bad_char}{suffix}"
        # If the bad char survives stripping (i.e. it's not whitespace at
        # an edge), the validator must reject. We assert rejection for the
        # general case where prefix/suffix are non-empty.
        with pytest.raises(ValueError):
            Credentials.from_oauth_token(
                token=token,
                project_id=project_id,
                region=cast(RegionType, region),
            )
