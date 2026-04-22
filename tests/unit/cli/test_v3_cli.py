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

from mixpanel_data._internal.config_v3 import ConfigManager
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
        """`mp session` prints account/project/workspace lines."""
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
        assert "account:" in result.output
        assert "project:" in result.output
        assert "workspace:" in result.output

    def test_session_json_format(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``mp session --format json`` emits a JSON-parseable ActiveSession."""
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
        assert payload.get("account") == "a"


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
