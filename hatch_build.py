"""Hatch build hook to include frontend assets in the wheel."""

from __future__ import annotations

import shutil
from pathlib import Path


def packaged_frontend_paths(root: Path) -> tuple[Path, Path]:
    src = root / "frontend" / "dist"
    dest = root / "src" / "otel_agent" / "dashboard" / "frontend_dist"
    return src, dest


def sync_packaged_frontend(root: Path) -> str:
    """Keep committed dashboard assets unless they are missing.

    ``frontend/dist`` is gitignored and often a leftover Vite build. Copying it
    over ``src/otel_agent/dashboard/frontend_dist`` during ``uv tool install``
    ships that leftover instead of the assets committed on the branch.

    Returns one of: skipped, copied, kept.
    """
    src, dest = packaged_frontend_paths(root)
    dest_ready = dest.exists() and (dest / "index.html").exists()

    if dest_ready:
        return "kept"

    if not src.exists():
        return "skipped"

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return "copied"


try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:  # hatchling is a build-time dependency
    class BuildHookInterface:  # type: ignore[no-redef]
        pass


class FrontendBuildHook(BuildHookInterface):
    """Ship committed frontend_dist; copy Vite output only when it is missing."""

    def initialize(self, version, build_data):
        root = Path(self.root)
        action = sync_packaged_frontend(root)
        src, dest = packaged_frontend_paths(root)
        if action == "copied":
            self.app.display_info(f"Copied frontend/dist/ → {dest}")
        elif action == "kept" and src.exists():
            self.app.display_info(
                f"Kept {dest} (ignored leftover {src})"
            )
        elif action == "skipped":
            self.app.display_warning(
                f"frontend/dist/ not found at {src} — skipping frontend bundling"
            )
