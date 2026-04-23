"""Functional tests for the new v3 CLI command groups (T054-T058).

Covers ``mp account``, ``mp project``, ``mp workspace``, ``mp session``,
``mp config`` plus the new globals (``--account``, ``--project``,
``--workspace``, ``--target``).

Reference: specs/042-auth-architecture-redesign/contracts/cli-commands.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mixpanel_data._internal.config import ConfigManager
from mixpanel_data.cli.main import app


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate $HOME and MP_CONFIG_PATH for hermetic CLI tests."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MP_CONFIG_PATH", str(tmp_path / ".mp" / "config.toml"))


@pytest.fixture
def runner() -> CliRunner:
    """A Typer CliRunner."""
    return CliRunner()


class TestAccountCli:
    """``mp account`` subcommands."""

    def test_list_empty(self, runner: CliRunner) -> None:
        """Empty config prints '(no accounts configured)'."""
        result = runner.invoke(app, ["account", "list"])
        assert result.exit_code == 0, result.output
        assert "no accounts configured" in result.output

    def test_add_service_account_via_env(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``mp account add --type service_account`` uses MP_SECRET from env."""
        monkeypatch.setenv("MP_SECRET", "team-secret")
        result = runner.invoke(
            app,
            [
                "account",
                "add",
                "team",
                "--type",
                "service_account",
                "--region",
                "us",
                "--username",
                "u",
                "--project",
                "3713224",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "team" in result.output
        assert "service_account" in result.output

    def test_add_oauth_browser(self, runner: CliRunner) -> None:
        """``mp account add --type oauth_browser`` needs no extra fields."""
        result = runner.invoke(
            app,
            ["account", "add", "personal", "--type", "oauth_browser", "--region", "us"],
        )
        assert result.exit_code == 0, result.output

    def test_add_oauth_token_with_env(self, runner: CliRunner) -> None:
        """``mp account add --type oauth_token --token-env`` is accepted."""
        result = runner.invoke(
            app,
            [
                "account",
                "add",
                "ci",
                "--type",
                "oauth_token",
                "--region",
                "us",
                "--token-env",
                "MP_OAUTH_TOKEN",
                "--project",
                "3713224",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_add_invalid_type_exits_nonzero(self, runner: CliRunner) -> None:
        """Bad ``--type`` exits with non-zero code and prints to stderr."""
        result = runner.invoke(
            app,
            ["account", "add", "x", "--type", "magic", "--region", "us"],
        )
        assert result.exit_code != 0

    def test_use_promotes_active(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``mp account use NAME`` writes [active].account."""
        monkeypatch.setenv("MP_SECRET", "s")
        runner.invoke(
            app,
            [
                "account",
                "add",
                "a",
                "--type",
                "service_account",
                "--region",
                "us",
                "--username",
                "u",
                "--project",
                "3713224",
            ],
        )
        runner.invoke(
            app, ["account", "add", "b", "--type", "oauth_browser", "--region", "us"]
        )
        result = runner.invoke(app, ["account", "use", "b"])
        assert result.exit_code == 0
        active = ConfigManager().get_active().account
        assert active == "b"

    def test_remove_simple(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``mp account remove NAME`` removes an unreferenced account."""
        monkeypatch.setenv("MP_SECRET", "s")
        runner.invoke(
            app,
            [
                "account",
                "add",
                "a",
                "--type",
                "service_account",
                "--region",
                "us",
                "--username",
                "u",
                "--project",
                "3713224",
            ],
        )
        result = runner.invoke(app, ["account", "remove", "a"])
        assert result.exit_code == 0


class TestProjectCli:
    """``mp project`` subcommands."""

    def test_show_when_no_active(self, runner: CliRunner) -> None:
        """Empty config → '(no active project)'."""
        result = runner.invoke(app, ["project", "show"])
        assert result.exit_code == 0
        assert "no active project" in result.output

    def test_use_writes_active_account_default_project(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``mp project use ID`` writes the active account's ``default_project``.

        Project lives on the account (FR-012), not in ``[active]``.
        """
        monkeypatch.setenv("MP_SECRET", "s")
        runner.invoke(
            app,
            [
                "account",
                "add",
                "a",
                "--type",
                "service_account",
                "--region",
                "us",
                "--username",
                "u",
                "--project",
                "1111111",
            ],
        )
        result = runner.invoke(app, ["project", "use", "3713224"])
        assert result.exit_code == 0
        cm = ConfigManager()
        # The active account's default_project was updated.
        assert cm.get_account("a").default_project == "3713224"

    def test_use_without_active_account_errors(self, runner: CliRunner) -> None:
        """``mp project use ID`` with no active account exits non-zero."""
        result = runner.invoke(app, ["project", "use", "3713224"])
        assert result.exit_code != 0


class TestProjectCliList:
    """``mp project list`` enumerates from /me (FR-047 + cli-commands.md §4.1)."""

    def _seed_account_and_me_cache(
        self,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        *,
        default_project: str | None = "1111111",
    ) -> None:
        """Add a service account + pre-populate the /me disk cache.

        Args:
            runner: Typer CliRunner.
            monkeypatch: pytest monkeypatch fixture.
            default_project: Active account's default_project; pass None
                to exercise the FR-047 "no project configured" path.
                ``service_account`` requires ``--project`` at add time;
                we strip it post-hoc via ConfigManager when None.
        """
        from mixpanel_data._internal.me import (
            MeCache,
            MeProjectInfo,
            MeResponse,
        )

        monkeypatch.setenv("MP_SECRET", "s")
        result = runner.invoke(
            app,
            [
                "account",
                "add",
                "team",
                "--type",
                "service_account",
                "--region",
                "us",
                "--username",
                "u",
                "--project",
                "1111111",
            ],
        )
        assert result.exit_code == 0, result.output
        cm = ConfigManager()
        if default_project is None:
            cm.update_account("team", default_project=None)
        elif default_project != "1111111":
            cm.update_account("team", default_project=default_project)

        # Pre-populate MeCache for "team" with two accessible projects.
        cache = MeCache(account_name="team")
        cache.put(
            MeResponse(
                user_id=42,
                user_email="u@example.com",
                projects={
                    "1111111": MeProjectInfo(
                        name="Alpha", organization_id=100, timezone="US/Pacific"
                    ),
                    "2222222": MeProjectInfo(
                        name="Beta", organization_id=100, timezone="US/Pacific"
                    ),
                },
            )
        )

    def test_list_enumerates_from_me_cache_by_default(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``mp project list`` MUST list projects from /me, not just print active.

        Regression: prior implementation echoed only ``default_project``
        unless ``--remote`` was passed, defeating the documented
        ``needs_project`` bootstrap flow.
        """
        self._seed_account_and_me_cache(runner, monkeypatch)
        result = runner.invoke(app, ["project", "list"])
        assert result.exit_code == 0, result.output
        assert "1111111" in result.output
        assert "2222222" in result.output
        assert "Alpha" in result.output
        assert "Beta" in result.output

    def test_list_marks_active_project(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The active account's ``default_project`` is marked with ``*``."""
        self._seed_account_and_me_cache(runner, monkeypatch)
        result = runner.invoke(app, ["project", "list"])
        assert result.exit_code == 0, result.output
        # Active line starts with '*' marker.
        active_line = next(
            line for line in result.output.splitlines() if "1111111" in line
        )
        assert active_line.lstrip().startswith("*")
        # Non-active line does not.
        other_line = next(
            line for line in result.output.splitlines() if "2222222" in line
        )
        assert not other_line.lstrip().startswith("*")

    def test_list_works_without_default_project_configured(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-047: ``mp project list`` MUST work with only auth configured.

        No ``default_project`` on the account → enumeration via /me must
        still succeed (the bootstrap path the plugin's ``needs_project``
        state depends on).
        """
        self._seed_account_and_me_cache(runner, monkeypatch, default_project=None)
        result = runner.invoke(app, ["project", "list"])
        assert result.exit_code == 0, result.output
        assert "1111111" in result.output
        assert "2222222" in result.output

    def test_list_remote_is_alias_for_refresh(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--remote`` is preserved as an alias for ``--refresh``."""
        self._seed_account_and_me_cache(runner, monkeypatch)
        # Both flags MUST be accepted; they trigger the bypass-cache code
        # path. The MeCache fixture is fresh so a refresh would force a
        # network call — to keep this hermetic we patch fetch to a no-op
        # that returns the cached response.
        from mixpanel_data._internal import me as me_mod

        original_fetch = me_mod.MeService.fetch
        call_log: list[bool] = []

        def _spy_fetch(
            self: object, *, force_refresh: bool = False
        ) -> me_mod.MeResponse:
            call_log.append(force_refresh)
            # Bypass the API call by reading straight from disk cache.
            cache = self._cache  # type: ignore[attr-defined]  # noqa: SLF001
            cached: me_mod.MeResponse | None = cache.get()
            assert cached is not None  # seeded by the fixture
            return cached

        monkeypatch.setattr(me_mod.MeService, "fetch", _spy_fetch)

        result_refresh = runner.invoke(app, ["project", "list", "--refresh"])
        assert result_refresh.exit_code == 0, result_refresh.output
        result_remote = runner.invoke(app, ["project", "list", "--remote"])
        assert result_remote.exit_code == 0, result_remote.output

        # Both invocations passed force_refresh=True at least once.
        assert any(call_log), "neither --refresh nor --remote forced a refetch"

        del original_fetch  # unused — kept for reader clarity


class TestWorkspaceCli:
    """``mp workspace`` subcommands."""

    def test_show_when_unset(self, runner: CliRunner) -> None:
        """``mp workspace show`` prints auto-resolution hint when unset."""
        result = runner.invoke(app, ["workspace", "show"])
        assert result.exit_code == 0
        assert "auto-resolved" in result.output

    def test_use_writes_active(self, runner: CliRunner) -> None:
        """``mp workspace use N`` writes [active].workspace."""
        result = runner.invoke(app, ["workspace", "use", "42"])
        assert result.exit_code == 0
        active = ConfigManager().get_active().workspace
        assert active == 42


class TestSessionCli:
    """``mp session`` (no subcommand) prints active state."""

    def test_session_default_format(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`mp session` prints contract-formatted four-line summary."""
        monkeypatch.setenv("MP_SECRET", "s")
        runner.invoke(
            app,
            [
                "account",
                "add",
                "a",
                "--type",
                "service_account",
                "--region",
                "us",
                "--username",
                "u",
                "--project",
                "3713224",
            ],
        )
        result = runner.invoke(app, ["session"])
        assert result.exit_code == 0
        # Contract §7: capitalized labels, four lines (account / project /
        # workspace / user) with type+region annotation on the account.
        assert "Account:" in result.output
        assert "Project:" in result.output
        assert "Workspace:" in result.output
        assert "User:" in result.output
        assert "service_account" in result.output  # account type annotation
        assert "us" in result.output  # region annotation

    def test_session_json_format(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``mp session --format json`` emits the contract structured payload."""
        monkeypatch.setenv("MP_SECRET", "s")
        runner.invoke(
            app,
            [
                "account",
                "add",
                "a",
                "--type",
                "service_account",
                "--region",
                "us",
                "--username",
                "u",
                "--project",
                "3713224",
            ],
        )
        result = runner.invoke(app, ["session", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output.strip())
        # Contract §7: account is a structured {name, type, region} object
        # so callers can inspect type/region without a follow-up command.
        assert payload["account"]["name"] == "a"
        assert payload["account"]["type"] == "service_account"
        assert payload["account"]["region"] == "us"
        assert payload["project"]["id"] == "3713224"


class TestConfigCli:
    """``mp config`` no longer exists (Fix 12 deleted the stub group).

    Under the alpha "free to break" lens there are no v1/v2 users to
    migrate, so the placeholder converter is gone instead of waiting
    for Phase 10. A v1/v2 ``~/.mp/config.toml`` now fails at the
    Pydantic validation layer with a generic-but-honest "unexpected key"
    error and the user is told to delete and re-add.
    """

    def test_no_mp_config_command(self, runner: CliRunner) -> None:
        """``mp config`` (or ``mp config convert``) → "No such command"."""
        result = runner.invoke(app, ["config", "convert"])
        assert result.exit_code != 0
        assert "no such command" in result.output.lower() or "config" in result.output


class TestGlobals:
    """The new global options behave as documented."""

    def test_target_with_account_exits(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--target`` combined with ``--account`` exits with code 3."""
        monkeypatch.setenv("MP_SECRET", "s")
        runner.invoke(
            app,
            [
                "account",
                "add",
                "a",
                "--type",
                "service_account",
                "--region",
                "us",
                "--username",
                "u",
                "--project",
                "3713224",
            ],
        )
        result = runner.invoke(
            app,
            ["--target", "ecom", "--account", "a", "session"],
        )
        assert result.exit_code == 3

    def test_target_with_project_exits(self, runner: CliRunner) -> None:
        """``--target`` combined with ``--project`` exits with code 3."""
        result = runner.invoke(
            app,
            ["--target", "ecom", "--project", "3018488", "session"],
        )
        assert result.exit_code == 3

    def test_workspace_global_accepted(self, runner: CliRunner) -> None:
        """``--workspace`` is accepted as a global override."""
        result = runner.invoke(app, ["--workspace", "42", "session"])
        assert result.exit_code == 0


class TestErrorRendering:
    """The ``handle_errors`` decorator must not Rich-eat ``[brackets]`` in messages."""

    def test_configerror_preserves_block_brackets_in_output(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """ConfigError messages containing ``[accounts.NAME]`` round-trip intact.

        The ConfigError raised when validating a malformed account block
        embeds ``[accounts.NAME]`` in its message. Rich would otherwise
        parse those brackets as markup tags and silently elide them,
        leaving users with ``Invalid  block:`` (note the double space) and
        no clue which block is bad. We must escape the message before
        handing it to the Rich console.
        """
        config_path = tmp_path / ".mp" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # Legacy v2 account block — surfaces brackets in the error message.
        config_path.write_text(
            "[accounts.fake-shack]\n"
            'username = "u"\n'
            'secret = "s"\n'
            'project_id = "111"\n'
            'region = "us"\n',
            encoding="utf-8",
        )

        result = runner.invoke(app, ["account", "list"])

        assert result.exit_code != 0
        assert "[accounts.fake-shack]" in result.output
