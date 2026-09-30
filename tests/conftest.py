"""Suite-wide test hygiene for the model capability catalog.

Nothing in this suite may reach the network through the catalog backfill:
the default fetcher seam is replaced with one that reports "unreachable", so
any lookup triggered by production code paths answers with empty capabilities
exactly as an unavailable OpenRouter would. Tests that exercise the fetch
inject their own fetcher (see tests/test_model_capabilities.py) or patch
``otel_agent.model_capabilities.fetch_catalog`` themselves.
"""

import pytest

from otel_agent import model_capabilities


@pytest.fixture(autouse=True)
def _no_catalog_network(monkeypatch):
    monkeypatch.setattr(model_capabilities, "fetch_catalog", lambda: None)
