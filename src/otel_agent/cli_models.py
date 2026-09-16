"""Model catalogs read from a vendor CLI.

Some upstreams publish no catalog at all: the Codex subscription endpoint
answers ``{"models": []}`` even with a valid credential, so a provider
pointing at it contributes nothing to ``GET /v1/models`` and says nothing
about why. The installed vendor CLI does publish the authoritative catalog —
``codex debug models`` renders it as JSON — which is the same fix
``cursor_sidecar.list_cursor_cli_models`` applies for Cursor. Unlike that one,
the source is *declared on the provider row* (``models_from``) and looked up
here, so a vendor is named in exactly one place and no code branches on a
provider name.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Callable

logger = logging.getLogger(__name__)

CODEX_CLI = "codex-cli"

CLI_TIMEOUT = 20.0
"""Bounded like the Cursor reader's: the vendor's own command is fast, and a
hung one must not hold the /v1/models request open."""


def parse_codex_catalog(text: str) -> list[str] | None:
    """Parse ``codex debug models`` JSON into model ids — the ``slug`` field.

    Returns None when the text is not the catalog document at all; entries
    without a usable slug are dropped. The gateway has no opinion about which
    models a vendor has, so nothing here filters the vendor's own list.
    """
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("models")
    if not isinstance(raw, list):
        return None

    ids: dict[str, None] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        ids[slug.strip()] = None  # insertion-ordered, so this de-duplicates
    return list(ids)


def list_codex_cli_models() -> list[str] | None:
    """Run ``codex debug models`` and return its model slugs.

    None — not an empty list — when the CLI could not be read: not installed,
    a non-zero exit, or output that is not the catalog. The caller falls back
    to the path it used before the declaration existed.
    """
    binary = shutil.which("codex")
    if not binary:
        logger.warning("Codex model catalog skipped: `codex` is not on PATH")
        return None
    try:
        proc = subprocess.run(
            [binary, "debug", "models"],
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("Codex model catalog unreadable: %s", e)
        return None
    if proc.returncode != 0:
        logger.warning("`codex debug models` exited %d", proc.returncode)
        return None
    ids = parse_codex_catalog(proc.stdout or "")
    if ids is None:
        logger.warning("`codex debug models` output was not a model catalog")
    return ids


#: Declared source name -> reader. This table is the only place a CLI source
#: is named; a provider row selects one by name, and everything else looks the
#: name up. Adding a second vendor CLI is a new row here.
#:
#: Readers take no provider and no credential. Deliberate for Codex: the
#: gateway's grant and the CLI's are two copies of one rotating chain and it
#: tolerates exactly one writer (see CONCEPTS.md, "Codex Grant"), so the
#: gateway must not push a bearer at the CLI.
MODEL_SOURCES: dict[str, Callable[[], list[str] | None]] = {
    CODEX_CLI: list_codex_cli_models,
}


def read_cli_models(name: str) -> list[str] | None:
    """Run the reader declared for *name*.

    None when *name* is not a declared source or its CLI could not be read, so
    the caller keeps the upstream behaviour it had before the field existed.
    """
    reader = MODEL_SOURCES.get(name)
    if reader is None:
        logger.warning(
            "Unknown models_from source %r. Declared sources: %s",
            name, ", ".join(repr(s) for s in sorted(MODEL_SOURCES)) or "none",
        )
        return None
    return reader()
