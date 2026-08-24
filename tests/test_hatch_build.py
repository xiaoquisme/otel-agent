"""Packaged dashboard assets must survive a local uv/hatch install."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hatch_build import sync_packaged_frontend


def _write_index(directory: Path, marker: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.html").write_text(f"<html>{marker}</html>", encoding="utf-8")


def test_sync_keeps_packaged_frontend_when_local_vite_dist_is_stale(tmp_path: Path) -> None:
    """A leftover frontend/dist must not replace committed frontend_dist."""
    dest = tmp_path / "src" / "otel_agent" / "dashboard" / "frontend_dist"
    src = tmp_path / "frontend" / "dist"
    _write_index(dest, "Download JSON")
    _write_index(src, "stale vite build")

    action = sync_packaged_frontend(tmp_path)

    assert action == "kept"
    assert "Download JSON" in (dest / "index.html").read_text(encoding="utf-8")
    assert "stale vite build" not in (dest / "index.html").read_text(encoding="utf-8")


def test_sync_copies_vite_dist_when_packaged_frontend_is_missing(tmp_path: Path) -> None:
    src = tmp_path / "frontend" / "dist"
    dest = tmp_path / "src" / "otel_agent" / "dashboard" / "frontend_dist"
    _write_index(src, "fresh build")

    action = sync_packaged_frontend(tmp_path)

    assert action == "copied"
    assert (dest / "index.html").read_text(encoding="utf-8") == "<html>fresh build</html>"


def test_sync_skips_when_neither_frontend_exists(tmp_path: Path) -> None:
    assert sync_packaged_frontend(tmp_path) == "skipped"
