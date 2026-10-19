"""otel-agent update — upgrade the installed CLI from its original channel.

Git installs are compared to the remote tip with ``git ls-remote`` before any
reinstall. The package version is not bumped on every commit, so version
equality is not the signal. Registry uv-tool installs are checked with
``uv pip install --dry-run`` and upgraded only when that resolution changes
the package. Local checkouts, editable installs, and container images are
left alone. A failed probe does not install.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from urllib.request import url2pathname

from otel_agent import __version__

GIT_INSTALL = "git+https://github.com/xiaoquisme/otel-agent.git"
GHCR_IMAGE = "ghcr.io/xiaoquisme/otel-agent:latest"
TOOL_NAME = "otel-agent"
_CANONICAL_PATH = "xiaoquisme/otel-agent"
_COMMIT_REV = re.compile(r"^[0-9a-fA-F]{7,64}$")
_SCP_GIT = re.compile(r"^(?P<user>[^@]+)@(?P<host>[^:]+):(?P<path>.+)$")
_KEY_NAME = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class DistInfo:
    """Install metadata from ``*.dist-info`` (pip / uv pip)."""

    installer: str = ""
    editable: bool = False
    location: str = ""
    vcs: str = ""
    vcs_url: str = ""
    requested_revision: str = ""
    commit_id: str = ""
    direct_kind: str = ""  # "", "vcs", "file", "url", "invalid"


@dataclass(frozen=True)
class InstallFacts:
    """Where this process appears to have been installed from."""

    in_container: bool = False
    ephemeral_uv: bool = False
    receipt_exists: bool = False
    receipt_text: str | None = None
    dist: DistInfo | None = None
    python: str = sys.executable


@dataclass(frozen=True)
class GitProbe:
    """Compare an installed commit to a remote ref. ``ref`` None means HEAD."""

    url: str
    ref: str | None
    local_commit: str


@dataclass(frozen=True)
class RegistryProbe:
    """Resolve one index requirement without installing it."""

    requirement: str
    python: str


@dataclass(frozen=True)
class UpdatePlan:
    """Either an installer command to run, or guidance and no mutation."""

    execute: bool
    argv: tuple[str, ...]
    message: str
    probe: GitProbe | RegistryProbe | None = None


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of a pre-install check. ``status`` is current, update, or error."""

    status: str
    message: str


def handle_update(args) -> None:
    """Upgrade this install when the probe says the remote is ahead."""
    del args  # reserved for future flags; the command takes none today
    before = f"otel-agent {__version__}"
    print(f"Current version: {before}")

    plan = plan_update(collect_install_facts())
    print(plan.message)
    if not plan.execute:
        sys.exit(1)

    outcome = probe_update(plan)
    print(outcome.message)
    if outcome.status == "error":
        print("The install was not changed.")
        if plan.argv:
            print("Reinstall manually:")
            print("  " + shlex.join(plan.argv))
        sys.exit(1)
    if outcome.status == "current":
        return
    if outcome.status != "update":
        print("The install was not changed.")
        sys.exit(1)

    if plan.argv and plan.argv[0] == "uv" and not _uv_on_path():
        print("uv is not on PATH, so the install was not changed.")
        print("Install uv, then rerun `otel-agent update`, or run:")
        print("  " + shlex.join(plan.argv))
        sys.exit(1)

    print("$ " + shlex.join(plan.argv))
    code = _run(plan.argv)
    if code != 0:
        print(f"Update command exited {code}.")
        sys.exit(code)

    after = _installed_version_line()
    if after:
        print(f"Updated version: {after}")
        if after == before:
            print(
                "The version string is unchanged. The package version is not "
                "bumped on every commit, so a matching string still means the "
                "installer ran."
            )
    else:
        print("Update finished. Read the new version with: otel-agent --version")
    print("If the gateway is already running, restart it: otel-agent proxy restart")


def plan_update(facts: InstallFacts) -> UpdatePlan:
    """Choose an upgrade command from install facts. Does not touch the network."""
    if facts.ephemeral_uv and not facts.receipt_exists:
        return UpdatePlan(False, (), _uvx_message())
    if facts.receipt_exists:
        return _plan_from_receipt(
            facts.receipt_text,
            local_commit=_local_commit(facts.dist),
            python=facts.python,
        )
    # The published image is a pip install of the build context, not a git
    # checkout. Recreating the container is the upgrade. A git install inside
    # a container can still be reinstalled in place.
    if facts.in_container and not _dist_is_git(facts.dist):
        return UpdatePlan(False, (), _container_message())
    if facts.dist is not None:
        return _plan_from_dist(facts.dist, facts.python)
    return UpdatePlan(False, (), _unknown_message(facts.python))


def _dist_is_git(dist: DistInfo | None) -> bool:
    return dist is not None and dist.direct_kind == "vcs" and dist.vcs == "git"


def collect_install_facts() -> InstallFacts:
    """Read the uv receipt and dist-info for this interpreter."""
    prefix = Path(sys.prefix)
    exists, text = read_tool_receipt(prefix)
    return InstallFacts(
        in_container=running_in_container(),
        ephemeral_uv=prefix_is_uv_cache(prefix),
        receipt_exists=exists,
        receipt_text=text,
        dist=read_dist_info(),
        python=sys.executable,
    )


def read_tool_receipt(prefix: Path) -> tuple[bool, str | None]:
    """Return ``(exists, text)``. Text is ``None`` when the file cannot be read."""
    path = prefix / "uv-receipt.toml"
    if not path.is_file():
        return False, None
    try:
        return True, path.read_text(encoding="utf-8")
    except OSError:
        return True, None


def running_in_container() -> bool:
    """True when this process is inside Docker, Podman, or Kubernetes."""
    dockerenv = Path("/.dockerenv").exists()
    containerenv = Path("/.containerenv").exists() or Path("/run/.containerenv").exists()
    cgroup = ""
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="replace")
    except OSError:
        cgroup = ""
    kubernetes = bool(os.environ.get("KUBERNETES_SERVICE_HOST"))
    return in_container(dockerenv, containerenv, cgroup, kubernetes)


def in_container(dockerenv: bool, containerenv: bool, cgroup_text: str, kubernetes: bool) -> bool:
    """Pure container check used by :func:`running_in_container`."""
    if dockerenv or containerenv or kubernetes:
        return True
    lowered = cgroup_text.lower()
    return any(token in lowered for token in ("docker", "containerd", "kubepods", "podman", "libpod"))


def prefix_is_uv_cache(prefix: Path) -> bool:
    """True for a disposable ``uvx`` environment, not a ``uv tool install``."""
    blob = "/".join(part.lower() for part in prefix.parts)
    if "/uv/" not in f"/{blob}/" and not blob.endswith("/uv"):
        return False
    return "archive-v" in blob or "environments-v" in blob


def read_dist_info() -> DistInfo | None:
    """Return dist-info for the installed package, or ``None`` if it is missing."""
    try:
        from importlib.metadata import PackageNotFoundError, distribution
    except ImportError:  # pragma: no cover - importlib.metadata is stdlib on 3.10+
        return None
    try:
        dist = distribution(TOOL_NAME)
    except PackageNotFoundError:
        return None
    return dist_info_from_metadata(dist.read_text("INSTALLER"), dist.read_text("direct_url.json"))


def dist_info_from_metadata(installer: str | None, direct_raw: str | None) -> DistInfo:
    """Parse installer name and PEP 610 ``direct_url.json`` contents."""
    info = DistInfo(installer=(installer or "").strip().lower())
    if direct_raw is None or not direct_raw.strip():
        return info
    try:
        data = json.loads(direct_raw)
    except json.JSONDecodeError:
        return DistInfo(installer=info.installer, direct_kind="invalid")
    if not isinstance(data, dict):
        return DistInfo(installer=info.installer, direct_kind="invalid")

    url = str(data.get("url") or "")
    dir_info = data.get("dir_info") if isinstance(data.get("dir_info"), dict) else {}
    vcs_info = data.get("vcs_info") if isinstance(data.get("vcs_info"), dict) else {}
    editable = bool(dir_info.get("editable"))
    if vcs_info.get("vcs"):
        return DistInfo(
            installer=info.installer,
            editable=editable,
            location=url,
            vcs=str(vcs_info.get("vcs") or ""),
            vcs_url=url,
            requested_revision=str(vcs_info.get("requested_revision") or ""),
            commit_id=str(vcs_info.get("commit_id") or ""),
            direct_kind="vcs",
        )
    if url.startswith("file:"):
        return DistInfo(
            installer=info.installer,
            editable=editable,
            location=_file_url_to_path(url),
            direct_kind="file",
        )
    if url:
        return DistInfo(
            installer=info.installer,
            editable=editable,
            location=url,
            direct_kind="url",
        )
    return DistInfo(installer=info.installer, editable=editable, direct_kind="invalid")


def parse_receipt_requirements(text: str) -> list[dict[str, str]] | None:
    """Parse ``requirements`` from a uv tool receipt.

    Returns ``None`` when the requirements cannot be read. uv writes them as
    an inline array of tables; ``[[tool.requirements]]`` is accepted too.
    """
    inline = _extract_bracket_block(text, "requirements")
    if inline is not None:
        return _parse_inline_tables(inline)
    tables = _parse_requirement_tables(text)
    if tables is not None:
        return tables
    return None


def git_install_spec(git_value: str, subdirectory: str | None = None) -> tuple[str, str | None]:
    """Build a ``git+`` install spec.

    Commit revisions are dropped so the reinstall follows the default branch.
    Branch and tag names are kept (``git+URL@name``). The canonical GitHub
    repository is normalized to the README https URL.
    """
    raw = git_value.strip()
    if raw.startswith("git+"):
        raw = raw[4:]

    scp = _SCP_GIT.match(raw)
    if scp and "://" not in raw:
        raw = f"ssh://{scp.group('user')}@{scp.group('host')}/{scp.group('path')}"

    parsed = urllib.parse.urlparse(raw)
    query = urllib.parse.parse_qs(parsed.query)
    rev = ""
    for key in ("rev", "tag", "branch"):
        values = query.get(key) or []
        if values and values[0]:
            rev = values[0]
            break
    sub = subdirectory or ""
    if not sub:
        sub_values = query.get("subdirectory") or []
        if sub_values:
            sub = sub_values[0]
    lfs = (query.get("lfs") or [""])[0]

    dropped: str | None = None
    if rev and _COMMIT_REV.match(rev):
        dropped = rev
        rev = ""

    if _is_canonical(parsed):
        base = "https://github.com/xiaoquisme/otel-agent.git"
    else:
        cleaned = parsed._replace(query="", fragment="")
        base = urllib.parse.urlunparse(cleaned)

    spec = "git+" + base
    if rev:
        spec += "@" + rev
    extras: list[str] = []
    if sub:
        extras.append("subdirectory=" + urllib.parse.quote(sub))
    if lfs:
        extras.append("lfs=" + urllib.parse.quote(lfs))
    if extras:
        spec += "?" + "&".join(extras)
    return spec, dropped


def _plan_from_receipt(text: str | None, *, local_commit: str, python: str) -> UpdatePlan:
    if text is None:
        return UpdatePlan(False, (), _unreadable_receipt_message())
    requirements = parse_receipt_requirements(text)
    if not requirements:
        return UpdatePlan(False, (), _unreadable_receipt_message())

    primary, extras = _split_primary(requirements)
    if "editable" in primary:
        return UpdatePlan(False, (), _editable_message(primary.get("editable", ""), uv_tool=True))
    local = primary.get("directory") or primary.get("path")
    if local:
        return UpdatePlan(
            False,
            (),
            _local_source_message(local, wheel=_looks_like_archive(local), uv_tool=True),
        )
    if "git" in primary and primary.get("git"):
        spec, dropped = git_install_spec(primary["git"], primary.get("subdirectory"))
        with_args: list[str] = []
        for extra in extras:
            rendered = _extra_spec(extra)
            if rendered is None:
                return UpdatePlan(False, (), _extras_message())
            with_args.extend(["--with", rendered])
        argv = ("uv", "tool", "install", "--upgrade", "--reinstall", *with_args, spec)
        installed = local_commit or (dropped or "")
        return UpdatePlan(True, argv, _git_message(spec, dropped), _git_probe(spec, installed))
    if primary.get("url"):
        return UpdatePlan(False, (), _pinned_url_message(primary["url"]))
    if not primary.get("name"):
        return UpdatePlan(False, (), _unreadable_receipt_message())

    specifier = primary.get("specifier", "")
    argv = ("uv", "tool", "upgrade", TOOL_NAME)
    return UpdatePlan(
        True,
        argv,
        _registry_message(specifier),
        RegistryProbe(requirement=f"{TOOL_NAME}{specifier}", python=python),
    )


def _plan_from_dist(dist: DistInfo, python: str) -> UpdatePlan:
    if dist.direct_kind == "invalid":
        return UpdatePlan(False, (), _unknown_message(python))
    if dist.editable:
        return UpdatePlan(False, (), _editable_message(dist.location, uv_tool=False))
    if dist.direct_kind == "file" and dist.location:
        return UpdatePlan(
            False,
            (),
            _local_source_message(
                dist.location,
                wheel=_looks_like_archive(dist.location),
                uv_tool=False,
                python=python,
            ),
        )
    if dist.direct_kind == "vcs":
        if dist.vcs != "git" or not dist.vcs_url:
            return UpdatePlan(False, (), _unknown_message(python))
        spec, dropped = git_install_spec(dist.vcs_url)
        revision = dist.requested_revision
        if revision and _COMMIT_REV.match(revision):
            dropped = dropped or revision
        elif revision:
            spec = _append_rev(spec, revision)
        argv = _pip_argv(python, dist.installer, spec)
        installed = _local_commit(dist) or (dropped or "")
        return UpdatePlan(
            True,
            argv,
            _pip_git_message(spec, dropped=dropped, revision=revision, installer=dist.installer),
            _git_probe(spec, installed),
        )
    if dist.direct_kind == "url":
        return UpdatePlan(False, (), _pinned_url_message(dist.location))
    return UpdatePlan(False, (), _unknown_message(python))


def _pip_argv(python: str, installer: str, spec: str) -> tuple[str, ...]:
    if installer.startswith("uv"):
        return ("uv", "pip", "install", "--upgrade", "--reinstall", "--python", python, spec)
    return (python, "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-cache-dir", spec)


def _split_primary(requirements: list[dict[str, str]]) -> tuple[dict[str, str], list[dict[str, str]]]:
    for index, req in enumerate(requirements):
        if _norm_name(req.get("name", "")) == TOOL_NAME:
            return req, requirements[:index] + requirements[index + 1 :]
    return requirements[0], requirements[1:]


def _extra_spec(req: dict[str, str]) -> str | None:
    if any(key in req for key in ("editable", "directory", "path")):
        return None
    name = req.get("name", "")
    if "git" in req:
        spec, _dropped = git_install_spec(req["git"], req.get("subdirectory"))
        return f"{name} @ {spec}" if name else spec
    if "url" in req:
        return f"{name} @ {req['url']}" if name else req["url"]
    if not name:
        return None
    return f"{name}{req.get('specifier', '')}"


def _git_message(spec: str, dropped_rev: str | None) -> str:
    lines = [
        "Installed with uv tool from git.",
        "A plain `uv tool upgrade` can leave a git install unchanged when the package version does not move.",
    ]
    if dropped_rev:
        lines.append(
            f"The receipt pinned commit {dropped_rev}; an update follows the default branch instead."
        )
    lines.append(f"Source: {spec}")
    return "\n".join(lines)


def _pip_git_message(spec: str, *, dropped: str | None, revision: str, installer: str) -> str:
    tool = "uv pip" if installer.startswith("uv") else "pip"
    lines = [
        f"Installed with {tool} from git.",
        "The package version is not bumped on every commit, so the installed commit is compared to the remote tip.",
    ]
    if revision and not _COMMIT_REV.match(revision):
        lines.append(f"Tracking revision {revision}.")
    else:
        commit = dropped or revision
        if commit:
            lines.append(
                f"Recorded commit {commit} is compared with the default branch tip."
            )
    lines.append(f"Source: {spec}")
    return "\n".join(lines)


def _registry_message(specifier: str) -> str:
    lines = [
        f"Installed with uv tool from a package index. Upgrading `{TOOL_NAME}` within that receipt.",
    ]
    if specifier:
        lines.append(
            f"The receipt records version constraint `{specifier}`. "
            "uv keeps that constraint on upgrade."
        )
        lines.append("To switch to the project git source instead:")
        lines.append(f"  uv tool install --upgrade --reinstall {GIT_INSTALL}")
    return "\n".join(lines)


def _container_message() -> str:
    return "\n".join([
        "This copy of otel-agent is running inside a container, so nothing was changed.",
        "Update the image, then recreate the container:",
        f"  docker pull {GHCR_IMAGE}",
        "  docker compose pull && docker compose up -d",
    ])


def _uvx_message() -> str:
    return "\n".join([
        "This process is a temporary uvx environment, so nothing was changed.",
        "The next uvx run resolves the git source again:",
        f"  uvx --from {GIT_INSTALL} otel-agent --version",
        "To install a copy that `otel-agent update` can upgrade:",
        f"  uv tool install {GIT_INSTALL}",
    ])


def _editable_message(location: str, *, uv_tool: bool) -> str:
    where = f" from {location}" if location else ""
    lines = [
        f"otel-agent is an editable install{where}, so nothing was changed.",
        "Pull that checkout yourself. This command will not replace it.",
    ]
    if uv_tool and location:
        lines.append(f"  uv tool install --editable --reinstall {shlex.quote(location)}")
    lines.append("To switch to the project git source instead:")
    lines.append(f"  uv tool install --upgrade --reinstall {GIT_INSTALL}")
    lines.append(f"  python -m pip install --upgrade --force-reinstall --no-cache-dir {GIT_INSTALL}")
    return "\n".join(lines)


def _local_source_message(
    location: str,
    *,
    wheel: bool,
    uv_tool: bool,
    python: str = "python",
) -> str:
    kind = "a local file" if wheel else "a local directory"
    quoted = shlex.quote(location)
    lines = [
        f"otel-agent was installed from {kind} ({location}), so nothing was changed.",
    ]
    if wheel:
        lines.append("Rebuild that file and reinstall it, or switch to the git source:")
    else:
        lines.append("Update that checkout, then reinstall it:")
        lines.append(f"  git -C {quoted} pull")
        if uv_tool:
            lines.append(f"  uv tool install --reinstall {quoted}")
        else:
            lines.append(
                f"  {python} -m pip install --upgrade --force-reinstall --no-cache-dir {quoted}"
            )
        lines.append("Or switch to the project git source:")
    lines.append(f"  uv tool install --upgrade --reinstall {GIT_INSTALL}")
    return "\n".join(lines)


def _append_rev(spec: str, rev: str) -> str:
    """Attach ``@rev`` when the last path segment does not already have one."""
    base, sep, query = spec.partition("?")
    tail = base.rsplit("/", 1)[-1]
    if "@" in tail:
        return spec
    rebuilt = f"{base}@{rev}"
    if sep:
        rebuilt += "?" + query
    return rebuilt


def _pinned_url_message(url: str) -> str:
    return "\n".join([
        f"otel-agent was installed from a direct URL ({url}), so nothing was changed.",
        "Reinstall that URL yourself, or switch to the project git source:",
        f"  uv tool install --upgrade --reinstall {GIT_INSTALL}",
        f"  python -m pip install --upgrade --force-reinstall --no-cache-dir {GIT_INSTALL}",
    ])


def _extras_message() -> str:
    return "\n".join([
        "The uv tool receipt includes extra requirements that cannot be rebuilt safely, so nothing was changed.",
        "Ask uv to reuse the receipt:",
        f"  uv tool upgrade {TOOL_NAME} --reinstall",
        "To switch to the project git source (this drops those extras):",
        f"  uv tool install --upgrade --reinstall {GIT_INSTALL}",
    ])


def _unreadable_receipt_message() -> str:
    return "\n".join([
        "Found a uv tool receipt but could not read its requirements, so nothing was changed.",
        "If this was a local checkout, update that checkout and reinstall it.",
        "To reinstall the project git source:",
        f"  uv tool install --upgrade --reinstall {GIT_INSTALL}",
        "To let uv reuse the receipt as-is:",
        f"  uv tool upgrade {TOOL_NAME} --reinstall",
    ])


def _unknown_message(python: str) -> str:
    return "\n".join([
        "Could not tell how this otel-agent was installed, so nothing was changed.",
        "uv tool:",
        f"  uv tool install --upgrade --reinstall {GIT_INSTALL}",
        "pip:",
        f"  {python} -m pip install --upgrade --force-reinstall --no-cache-dir {GIT_INSTALL}",
        "Docker / GHCR:",
        f"  docker pull {GHCR_IMAGE}",
    ])


def _local_commit(dist: DistInfo | None) -> str:
    """Installed git commit from dist-info, or a requested SHA if that is all we have."""
    if dist is None:
        return ""
    if dist.commit_id and _COMMIT_REV.match(dist.commit_id):
        return dist.commit_id
    if dist.requested_revision and _COMMIT_REV.match(dist.requested_revision):
        return dist.requested_revision
    return ""


def _git_probe(spec: str, local_commit: str) -> GitProbe:
    url, ref = git_remote_from_spec(spec)
    return GitProbe(url=url, ref=ref, local_commit=local_commit)


def git_remote_from_spec(spec: str) -> tuple[str, str | None]:
    """Split a ``git+`` install spec into a clone URL and an optional ref name.

    A missing ref means the default branch (``HEAD``). A commit SHA is not a
    ref here; those specs already follow the default branch.
    """
    raw = spec[4:] if spec.startswith("git+") else spec
    base = raw.split("?", 1)[0].split("#", 1)[0]
    tail = base.rsplit("/", 1)[-1]
    ref: str | None = None
    if "@" in tail:
        path, ref = tail.rsplit("@", 1)
        base = base[: -len(tail)] + path
        if not ref or _COMMIT_REV.match(ref):
            ref = None
    return base, ref


def probe_update(plan: UpdatePlan) -> ProbeResult:
    """Ask the remote whether ``plan`` would change this install. No install."""
    if isinstance(plan.probe, GitProbe):
        return probe_git(plan.probe)
    if isinstance(plan.probe, RegistryProbe):
        return probe_registry(plan.probe)
    return ProbeResult("error", "This install has no update probe, so nothing was installed.")


def probe_git(probe: GitProbe) -> ProbeResult:
    """Compare the installed commit to ``git ls-remote`` for the tracked ref."""
    if not probe.local_commit:
        return ProbeResult(
            "error",
            "The installed git commit is not recorded, so this command will not reinstall.",
        )
    if not probe.url:
        return ProbeResult("error", "The git remote URL is missing, so this command will not reinstall.")
    if not _git_on_path():
        return ProbeResult(
            "error",
            "git is not on PATH, so the remote revision could not be checked.",
        )
    if probe.ref is None:
        argv = ["git", "ls-remote", probe.url, "HEAD"]
    else:
        argv = [
            "git", "ls-remote", probe.url,
            f"refs/heads/{probe.ref}",
            f"refs/tags/{probe.ref}",
        ]
    code, out, err = _capture(argv)
    if code != 0:
        detail = (err or out).strip() or f"exit {code}"
        return ProbeResult("error", f"Could not read the remote git revision: {detail}")
    remote = parse_ls_remote(out, probe.ref)
    if not remote:
        label = probe.ref or "HEAD"
        return ProbeResult("error", f"git ls-remote returned no revision for {label}.")
    label = probe.ref or "HEAD"
    if _same_commit(probe.local_commit, remote):
        return ProbeResult("current", f"Already up to date at {remote} ({label}).")
    return ProbeResult(
        "update",
        f"Update available: {probe.local_commit} -> {remote} ({label}).",
    )


def probe_registry(probe: RegistryProbe) -> ProbeResult:
    """Resolve the index requirement with ``uv pip install --dry-run``."""
    if not probe.requirement:
        return ProbeResult("error", "The package requirement is missing, so nothing was installed.")
    if not _uv_on_path():
        return ProbeResult(
            "error",
            "uv is not on PATH, so the package index could not be checked.",
        )
    argv = [
        "uv", "pip", "install", "--dry-run", "--upgrade", "--no-deps",
        "--python", probe.python, probe.requirement,
    ]
    code, out, err = _capture(argv)
    text = f"{out}\n{err}"
    if code != 0:
        detail = (err or out).strip() or f"exit {code}"
        return ProbeResult("error", f"Could not resolve {probe.requirement}: {detail}")
    change = parse_dry_run_package(text, TOOL_NAME)
    if change == "unchanged":
        return ProbeResult("current", f"Already up to date ({probe.requirement}).")
    if change is None:
        return ProbeResult(
            "error",
            "The index check did not say whether otel-agent would change, so nothing was installed.",
        )
    old, new = change
    if old == new:
        return ProbeResult("current", f"Already up to date at {new}.")
    shown_old = old or "unknown"
    return ProbeResult("update", f"Update available: {shown_old} -> {new}.")


def parse_ls_remote(text: str, ref: str | None) -> str | None:
    """Pick the commit from ``git ls-remote`` output.

    ``ref`` None selects ``HEAD``. A name prefers ``refs/heads/<name>``, then
    the peeled tag commit, then the tag object.
    """
    found: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if "\t" not in line:
            continue
        sha, name = line.split("\t", 1)
        sha = sha.strip()
        name = name.strip()
        if _COMMIT_REV.match(sha):
            found.append((sha, name))
    if not found:
        return None
    if ref is None:
        for sha, name in found:
            if name == "HEAD":
                return sha
        return None
    for sha, name in found:
        if name == f"refs/heads/{ref}":
            return sha
    peeled = "refs/tags/" + ref + "^{}"
    for sha, name in found:
        if name == peeled:
            return sha
    for sha, name in found:
        if name == f"refs/tags/{ref}":
            return sha
    return None


def parse_dry_run_package(text: str, name: str) -> str | tuple[str, str] | None:
    """Read a ``uv pip install --dry-run`` transcript for one package.

    Returns ``"unchanged"``, ``(old, new)`` when the package would change, or
    ``None`` when the transcript does not answer.
    """
    wanted = name.lower().replace("_", "-")
    old = ""
    new = ""
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) < 3 or stripped[1] != " ":
            continue
        sign = stripped[0]
        if sign not in "+-":
            continue
        body = stripped[2:]
        pkg, sep, version = body.partition("==")
        if not sep:
            continue
        if pkg.lower().replace("_", "-") != wanted:
            continue
        version = version.split()[0]
        if sign == "-":
            old = version
        else:
            new = version
    if new and new != old:
        return (old, new)
    if "Would make no changes" in text:
        return "unchanged"
    if new and new == old:
        return "unchanged"
    return None


def _same_commit(local: str, remote: str) -> bool:
    left = local.strip().lower()
    right = remote.strip().lower()
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 7 and _COMMIT_REV.match(shorter) and longer.startswith(shorter)


def _git_on_path() -> bool:
    return shutil.which("git") is not None


def _capture(argv: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """Run a probe command. Git credential prompts fail instead of waiting."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return 1, "", f"timed out after {timeout}s"
    except OSError as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _extract_bracket_block(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*\[", text)
    if not match:
        return None
    start = match.end() - 1
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index]
    return None


def _parse_inline_tables(body: str) -> list[dict[str, str]] | None:
    tables: list[dict[str, str]] = []
    depth = 0
    start: int | None = None
    for index, char in enumerate(body):
        if char == "{":
            if depth == 0:
                start = index + 1
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                tables.append(_parse_key_values(body[start:index]))
                start = None
            elif depth < 0:
                return None
    if depth != 0:
        return None
    return tables


def _parse_requirement_tables(text: str) -> list[dict[str, str]] | None:
    parts = re.split(r"(?m)^\[\[tool\.requirements\]\][ \t]*$", text)
    if len(parts) == 1:
        return None
    requirements: list[dict[str, str]] = []
    for part in parts[1:]:
        body = re.split(r"(?m)^\[", part, maxsplit=1)[0]
        req = _parse_key_values(body)
        if req:
            requirements.append(req)
    return requirements or None


def _parse_key_values(body: str) -> dict[str, str]:
    """Parse ``key = value`` pairs. Quoted values may contain spaces and ``\\``."""
    parsed: dict[str, str] = {}
    index = 0
    length = len(body)
    while index < length:
        while index < length and body[index] in " \t\r\n,":
            index += 1
        if index >= length:
            break
        if body[index] == "#":
            while index < length and body[index] not in "\r\n":
                index += 1
            continue
        key_match = _KEY_NAME.match(body, index)
        if not key_match:
            break
        key = key_match.group(0)
        index = key_match.end()
        while index < length and body[index] in " \t":
            index += 1
        if index >= length or body[index] != "=":
            break
        index += 1
        while index < length and body[index] in " \t":
            index += 1
        if index >= length:
            break
        if body[index] in "\"'":
            quote = body[index]
            index += 1
            chars: list[str] = []
            while index < length and body[index] != quote:
                if body[index] == "\\" and index + 1 < length:
                    chars.append(body[index + 1])
                    index += 2
                    continue
                chars.append(body[index])
                index += 1
            parsed[key] = "".join(chars)
            if index < length and body[index] == quote:
                index += 1
            continue
        start = index
        while index < length and body[index] not in ",}\r\n":
            index += 1
        parsed[key] = body[start:index].strip()
    return parsed


def _is_canonical(parsed: urllib.parse.ParseResult) -> bool:
    host = (parsed.hostname or "").lower()
    if host != "github.com":
        return False
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return path.lower() == _CANONICAL_PATH


def _file_url_to_path(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return url2pathname(urllib.parse.unquote(parsed.path))


def _looks_like_archive(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith((".whl", ".tar.gz", ".zip"))


def _norm_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _uv_on_path() -> bool:
    return shutil.which("uv") is not None


def _run(argv: tuple[str, ...]) -> int:
    completed = subprocess.run(list(argv))
    return completed.returncode


def _installed_version_line() -> str | None:
    for argv in _version_candidates():
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0:
            continue
        text = (proc.stdout or proc.stderr or "").strip()
        if text:
            return text.splitlines()[0].strip()
    return None


def _version_candidates() -> list[list[str]]:
    candidates: list[list[str]] = []
    seen: set[str] = set()
    resolved = shutil.which(TOOL_NAME)
    argv0 = sys.argv[0] if sys.argv else ""
    for path in (resolved, argv0):
        if not path or path in seen:
            continue
        if path != resolved and not Path(path).exists():
            continue
        seen.add(path)
        candidates.append([path, "--version"])
    candidates.append([
        sys.executable,
        "-c",
        "from otel_agent import __version__; print(f'otel-agent {__version__}')",
    ])
    return candidates
