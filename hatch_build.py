"""Hatch build hook to include frontend/dist/ in the wheel."""

from pathlib import Path
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FrontendBuildHook(BuildHookInterface):
    """Copy frontend/dist/ into the package so it ships with the wheel."""

    def initialize(self, version, build_data):
        root = Path(self.root)
        src = root / "frontend" / "dist"
        dest = root / "src" / "otel_agent" / "dashboard" / "frontend_dist"

        if not src.exists():
            self.app.display_warning(
                f"frontend/dist/ not found at {src} — skipping frontend bundling"
            )
            return

        import shutil

        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        self.app.display_info(f"Copied frontend/dist/ → {dest}")
