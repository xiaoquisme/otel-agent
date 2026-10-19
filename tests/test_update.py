"""Tests for `otel-agent update` planning and CLI wiring.

Installer commands are never executed for real — subprocess is mocked.
"""

import json
import sys
from pathlib import Path

import pytest

from otel_agent.cli import build_parser, main
from otel_agent.commands import update as update_mod
from otel_agent.commands.update import (
    GIT_INSTALL,
    DistInfo,
    InstallFacts,
    collect_install_facts,
    dist_info_from_metadata,
    git_install_spec,
    in_container,
    parse_receipt_requirements,
    plan_update,
    prefix_is_uv_cache,
    read_tool_receipt,
)


RECEIPT_GIT = """\
[tool]
requirements = [{ name = "otel-agent", git = "https://github.com/xiaoquisme/otel-agent.git" }]
entrypoints = [
    { name = "otel-agent", install-path = "/tmp/bin/otel-agent", from = "otel-agent" },
]
"""

RECEIPT_GIT_MAIN = """\
[tool]
requirements = [{ name = "otel-agent", git = "https://github.com/xiaoquisme/otel-agent.git?rev=main" }]
"""

RECEIPT_GIT_SHA = """\
[tool]
requirements = [{ name = "otel-agent", git = "https://github.com/xiaoquisme/otel-agent.git?rev=0123456789abcdef0123456789abcdef01234567" }]
"""

RECEIPT_FORK = """\
[tool]
requirements = [{ name = "otel-agent", git = "https://github.com/example/otel-agent.git?rev=dev" }]
"""

RECEIPT_EDITABLE = """\
[tool]
requirements = [{ name = "otel-agent", editable = "/src/otel-agent" }]
"""

RECEIPT_DIRECTORY = """\
[tool]
requirements = [{ name = "otel-agent", directory = "/src/otel-agent" }]
"""

RECEIPT_WHEEL = """\
[tool]
requirements = [{ name = "otel-agent", path = "/tmp/otel_agent-0.1.0-py3-none-any.whl" }]
"""

RECEIPT_REGISTRY = """\
[tool]
requirements = [{ name = "otel-agent", specifier = "==0.1.0" }]
"""

RECEIPT_WITH = """\
[tool]
requirements = [
    { name = "otel-agent", git = "https://github.com/xiaoquisme/otel-agent.git" },
    { name = "httpx", specifier = ">=0.28" },
]
"""

RECEIPT_TABLES = """\
[tool]

[[tool.requirements]]
name = "otel-agent"
git = "https://github.com/xiaoquisme/otel-agent.git"

[tool.options]
exclude-newer = "2024-03-25T00:00:00Z"
"""


def _facts(**overrides) -> InstallFacts:
    base = dict(
        in_container=False,
        ephemeral_uv=False,
        receipt_exists=False,
        receipt_text=None,
        dist=None,
        python="/usr/bin/python3",
    )
    base.update(overrides)
    return InstallFacts(**base)


def test_parser_update_subcommand():
    parser = build_parser()
    args = parser.parse_args(["update"])
    assert args.command == "update"


def test_parser_help_lists_update(capsys):
    parser = build_parser()
    parser.print_help()
    captured = capsys.readouterr()
    assert "update" in captured.out


def test_main_dispatches_update(monkeypatch):
    called = {}

    def fake_handle(args):
        called["command"] = args.command

    monkeypatch.setattr(sys, "argv", ["otel-agent", "update"])
    monkeypatch.setattr(update_mod, "handle_update", fake_handle)
    main()
    assert called["command"] == "update"


def test_parse_receipt_inline_git():
    reqs = parse_receipt_requirements(RECEIPT_GIT)
    assert reqs is not None
    assert reqs[0]["name"] == "otel-agent"
    assert reqs[0]["git"] == "https://github.com/xiaoquisme/otel-agent.git"


def test_parse_receipt_array_of_tables():
    reqs = parse_receipt_requirements(RECEIPT_TABLES)
    assert reqs == [{
        "name": "otel-agent",
        "git": "https://github.com/xiaoquisme/otel-agent.git",
    }]


def test_parse_receipt_missing_requirements():
    assert parse_receipt_requirements("[tool]\nentrypoints = []\n") is None


def test_parse_receipt_keeps_windows_directory():
    text = (
        '[tool]\n'
        'requirements = [{ name = "otel-agent", directory = "C:\\\\Users\\\\me\\\\otel-agent" }]\n'
    )
    reqs = parse_receipt_requirements(text)
    assert reqs is not None
    assert reqs[0]["directory"] == r"C:\Users\me\otel-agent"
    plan = plan_update(_facts(receipt_exists=True, receipt_text=text))
    assert plan.execute is False
    assert "local directory" in plan.message


def test_git_install_spec_canonical_and_fork():
    spec, dropped = git_install_spec("https://github.com/xiaoquisme/otel-agent.git")
    assert spec == GIT_INSTALL
    assert dropped is None

    spec, dropped = git_install_spec(
        "https://github.com/xiaoquisme/otel-agent.git?rev=0123456789abcdef0123456789abcdef01234567"
    )
    assert spec == GIT_INSTALL
    assert dropped == "0123456789abcdef0123456789abcdef01234567"

    spec, dropped = git_install_spec("git@github.com:xiaoquisme/otel-agent.git")
    assert spec == GIT_INSTALL
    assert dropped is None

    spec, dropped = git_install_spec("https://github.com/example/otel-agent.git?rev=dev")
    assert spec == "git+https://github.com/example/otel-agent.git@dev"
    assert dropped is None


def test_plan_uv_git_reinstalls_readme_url():
    plan = plan_update(_facts(receipt_exists=True, receipt_text=RECEIPT_GIT))
    assert plan.execute is True
    assert plan.argv == (
        "uv", "tool", "install", "--upgrade", "--reinstall", GIT_INSTALL,
    )
    assert "uv tool upgrade" in plan.message
    assert plan.argv[1:3] != ("tool", "upgrade")


def test_plan_uv_git_keeps_branch_and_drops_commit():
    main_plan = plan_update(_facts(receipt_exists=True, receipt_text=RECEIPT_GIT_MAIN))
    assert main_plan.argv[-1] == f"{GIT_INSTALL}@main"

    sha_plan = plan_update(_facts(receipt_exists=True, receipt_text=RECEIPT_GIT_SHA))
    assert sha_plan.argv[-1] == GIT_INSTALL
    assert "0123456789abcdef0123456789abcdef01234567" in sha_plan.message

    fork = plan_update(_facts(receipt_exists=True, receipt_text=RECEIPT_FORK))
    assert fork.argv[-1] == "git+https://github.com/example/otel-agent.git@dev"


def test_plan_uv_git_preserves_simple_extras():
    plan = plan_update(_facts(receipt_exists=True, receipt_text=RECEIPT_WITH))
    assert plan.argv == (
        "uv", "tool", "install", "--upgrade", "--reinstall",
        "--with", "httpx>=0.28",
        GIT_INSTALL,
    )


def test_plan_uv_editable_directory_and_wheel_do_not_run():
    editable = plan_update(_facts(receipt_exists=True, receipt_text=RECEIPT_EDITABLE))
    assert editable.execute is False
    assert "editable" in editable.message
    assert "/src/otel-agent" in editable.message

    directory = plan_update(_facts(receipt_exists=True, receipt_text=RECEIPT_DIRECTORY))
    assert directory.execute is False
    assert "local directory" in directory.message
    assert "git -C /src/otel-agent pull" in directory.message
    assert "uv tool install --reinstall /src/otel-agent" in directory.message

    wheel = plan_update(_facts(receipt_exists=True, receipt_text=RECEIPT_WHEEL))
    assert wheel.execute is False
    assert "local file" in wheel.message
    assert GIT_INSTALL in wheel.message


def test_plan_uv_registry_uses_upgrade():
    plan = plan_update(_facts(receipt_exists=True, receipt_text=RECEIPT_REGISTRY))
    assert plan.execute is True
    assert plan.argv == ("uv", "tool", "upgrade", "otel-agent")
    assert "==0.1.0" in plan.message


def test_plan_unreadable_receipt_refuses():
    missing = plan_update(_facts(receipt_exists=True, receipt_text=None))
    assert missing.execute is False
    assert "nothing was changed" in missing.message
    assert GIT_INSTALL in missing.message

    garbage = plan_update(_facts(receipt_exists=True, receipt_text="this is not a receipt"))
    assert garbage.execute is False


def test_plan_container_uvx_and_unknown_refuse():
    container = plan_update(_facts(
        in_container=True,
        dist=DistInfo(direct_kind="file", location="/src"),
    ))
    assert container.execute is False
    assert "docker pull ghcr.io/xiaoquisme/otel-agent:latest" in container.message
    assert "docker compose pull" in container.message

    # A uv tool install is upgraded even when the process is inside a container.
    receipt = plan_update(_facts(in_container=True, receipt_exists=True, receipt_text=RECEIPT_GIT))
    assert receipt.execute is True
    assert receipt.argv[-1] == GIT_INSTALL

    uvx = plan_update(_facts(ephemeral_uv=True, dist=DistInfo(direct_kind="vcs", vcs="git", vcs_url="https://github.com/xiaoquisme/otel-agent.git")))
    assert uvx.execute is False
    assert "uvx" in uvx.message

    unknown = plan_update(_facts())
    assert unknown.execute is False
    assert f"/usr/bin/python3 -m pip install --upgrade --force-reinstall --no-cache-dir {GIT_INSTALL}" in unknown.message


def test_plan_pip_git_and_uv_pip():
    dist = dist_info_from_metadata(
        "pip\n",
        json.dumps({
            "url": "https://github.com/xiaoquisme/otel-agent.git",
            "vcs_info": {
                "vcs": "git",
                "commit_id": "0123456789abcdef0123456789abcdef01234567",
                "requested_revision": "main",
            },
        }),
    )
    plan = plan_update(_facts(dist=dist))
    assert plan.execute is True
    assert plan.argv == (
        "/usr/bin/python3", "-m", "pip", "install",
        "--upgrade", "--force-reinstall", "--no-cache-dir",
        f"{GIT_INSTALL}@main",
    )
    assert "Tracking revision main." in plan.message

    uv_dist = DistInfo(
        installer="uv",
        vcs="git",
        vcs_url="https://github.com/example/otel-agent.git",
        requested_revision="0123456789abcdef0123456789abcdef01234567",
        direct_kind="vcs",
    )
    uv_plan = plan_update(_facts(dist=uv_dist))
    assert uv_plan.argv[:6] == ("uv", "pip", "install", "--upgrade", "--reinstall", "--python")
    assert uv_plan.argv[-1] == "git+https://github.com/example/otel-agent.git"
    assert "0123456789abcdef0123456789abcdef01234567" in uv_plan.message


def test_plan_pip_editable_and_local_file_refuse():
    editable = dist_info_from_metadata(
        "pip",
        json.dumps({"url": "file:///src/otel-agent", "dir_info": {"editable": True}}),
    )
    plan = plan_update(_facts(dist=editable))
    assert plan.execute is False
    assert "editable" in plan.message
    assert "/src/otel-agent" in plan.message

    local = dist_info_from_metadata(
        "pip",
        json.dumps({"url": "file:///src/otel-agent", "dir_info": {}}),
    )
    local_plan = plan_update(_facts(dist=local))
    assert local_plan.execute is False
    assert "local directory" in local_plan.message
    assert "python3 -m pip install" in local_plan.message


def test_plan_invalid_direct_url_refuses():
    dist = dist_info_from_metadata("pip", "{not json")
    plan = plan_update(_facts(dist=dist))
    assert plan.execute is False
    assert "nothing was changed" in plan.message


def test_container_and_uv_cache_helpers():
    assert in_container(True, False, "", False) is True
    assert in_container(False, False, "0::/init.scope", False) is False
    assert in_container(False, False, "0::/docker/abc", False) is True
    assert in_container(False, False, "", True) is True
    assert prefix_is_uv_cache(Path("/home/user/.cache/uv/archive-v0/abc")) is True
    assert prefix_is_uv_cache(Path("/home/user/.local/share/uv/tools/otel-agent")) is False


def test_read_tool_receipt(tmp_path):
    assert read_tool_receipt(tmp_path) == (False, None)
    receipt = tmp_path / "uv-receipt.toml"
    receipt.write_text(RECEIPT_GIT, encoding="utf-8")
    exists, text = read_tool_receipt(tmp_path)
    assert exists is True
    assert text is not None
    assert "otel-agent" in text


def test_handle_update_prints_versions_and_runs(monkeypatch, capsys):
    ran = {}

    def fake_run(argv):
        ran["argv"] = argv
        return 0

    monkeypatch.setattr(update_mod, "__version__", "0.1.0")
    monkeypatch.setattr(update_mod, "collect_install_facts", lambda: _facts(
        receipt_exists=True, receipt_text=RECEIPT_GIT,
    ))
    monkeypatch.setattr(update_mod, "_uv_on_path", lambda: True)
    monkeypatch.setattr(update_mod, "_run", fake_run)
    monkeypatch.setattr(update_mod, "_installed_version_line", lambda: "otel-agent 0.1.0")

    update_mod.handle_update(None)
    captured = capsys.readouterr()
    assert "Current version: otel-agent 0.1.0" in captured.out
    assert "Updated version: otel-agent 0.1.0" in captured.out
    assert "otel-agent proxy restart" in captured.out
    assert ran["argv"] == (
        "uv", "tool", "install", "--upgrade", "--reinstall", GIT_INSTALL,
    )
    assert "$ uv tool install --upgrade --reinstall" in captured.out


def test_handle_update_reports_a_new_version(monkeypatch, capsys):
    monkeypatch.setattr(update_mod, "__version__", "0.1.0")
    monkeypatch.setattr(update_mod, "collect_install_facts", lambda: _facts(
        receipt_exists=True, receipt_text=RECEIPT_GIT,
    ))
    monkeypatch.setattr(update_mod, "_uv_on_path", lambda: True)
    monkeypatch.setattr(update_mod, "_run", lambda argv: 0)
    monkeypatch.setattr(update_mod, "_installed_version_line", lambda: "otel-agent 0.2.0")

    update_mod.handle_update(None)
    captured = capsys.readouterr()
    assert "Updated version: otel-agent 0.2.0" in captured.out
    assert "version string is unchanged" not in captured.out


def test_handle_update_refuses_without_subprocess(monkeypatch, capsys):
    def fail_run(argv):
        raise AssertionError(f"should not run {argv}")

    monkeypatch.setattr(update_mod, "collect_install_facts", lambda: _facts(in_container=True))
    monkeypatch.setattr(update_mod, "_run", fail_run)

    with pytest.raises(SystemExit) as exc:
        update_mod.handle_update(None)
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Current version:" in captured.out
    assert "docker pull" in captured.out
    assert "Updated version:" not in captured.out


def test_handle_update_missing_uv(monkeypatch, capsys):
    def fail_run(argv):
        raise AssertionError(f"should not run {argv}")

    monkeypatch.setattr(update_mod, "collect_install_facts", lambda: _facts(
        receipt_exists=True, receipt_text=RECEIPT_GIT,
    ))
    monkeypatch.setattr(update_mod, "_uv_on_path", lambda: False)
    monkeypatch.setattr(update_mod, "_run", fail_run)

    with pytest.raises(SystemExit) as exc:
        update_mod.handle_update(None)
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "uv is not on PATH" in captured.out
    assert GIT_INSTALL in captured.out


def test_handle_update_command_failure(monkeypatch, capsys):
    monkeypatch.setattr(update_mod, "collect_install_facts", lambda: _facts(
        receipt_exists=True, receipt_text=RECEIPT_GIT,
    ))
    monkeypatch.setattr(update_mod, "_uv_on_path", lambda: True)
    monkeypatch.setattr(update_mod, "_run", lambda argv: 2)

    with pytest.raises(SystemExit) as exc:
        update_mod.handle_update(None)
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "exited 2" in captured.out
    assert "Updated version:" not in captured.out


def test_installed_version_line_reads_stdout(monkeypatch):
    class Proc:
        returncode = 0
        stdout = "otel-agent 9.9.9\n"
        stderr = ""

    def fake_run(argv, **kwargs):
        assert argv[-1] == "--version" or argv[1] == "-c"
        return Proc()

    monkeypatch.setattr(update_mod.shutil, "which", lambda name: "/tmp/otel-agent")
    monkeypatch.setattr(update_mod.subprocess, "run", fake_run)
    assert update_mod._installed_version_line() == "otel-agent 9.9.9"


def test_installed_version_line_skips_failures(monkeypatch):
    def fake_run(argv, **kwargs):
        if argv[-1] == "--version":
            raise OSError("missing")
        proc = type("Proc", (), {})()
        proc.returncode = 0
        proc.stdout = "otel-agent 1.2.3\n"
        proc.stderr = ""
        return proc

    monkeypatch.setattr(update_mod.shutil, "which", lambda name: "/no/such/otel-agent")
    monkeypatch.setattr(update_mod.subprocess, "run", fake_run)
    assert update_mod._installed_version_line() == "otel-agent 1.2.3"


def test_collect_install_facts_does_not_touch_network():
    facts = collect_install_facts()
    plan = plan_update(facts)
    assert isinstance(plan.execute, bool)
    assert plan.message
