---
title: "Fix Broken Integration Test After SSE Removal"
date: "2026-07-13"
category: "test-failures"
module: "dashboard"
problem_type: "test_failure"
component: "testing_framework"
severity: "medium"
symptoms:
  - "test_integration.py fails with AttributeError on api.get_max_id()"
  - "test_integration.py fails with AttributeError on api.get_requests_since()"
root_cause: "incomplete_setup"
resolution_type: "test_fix"
tags:
  - "dashboard"
  - "sse"
  - "test"
  - "integration-test"
  - "broken-test"
  - "refactor-oversight"
---

# Fix Broken Integration Test After SSE Removal

## Problem

When SSE was removed from the dashboard (PR #1), the `get_max_id()` and `get_requests_since()` methods were deleted from four backend files:

- `src/otel_agent/dashboard/api.py`
- `src/otel_agent/storage/base.py`
- `src/otel_agent/storage/duckdb.py`
- `src/otel_agent/storage/sqlite.py`

The unit tests in `tests/test_dashboard.py` were updated as part of that change — `test_get_requests_since`, `test_get_max_id`, and `test_get_max_id_empty` were removed and a `test_route_events_removed` verifying 404 was added. However, the integration test file `tests/test_integration.py` was missed. Lines 347–351 still call the deleted methods, causing the integration test suite to fail with `AttributeError`.

## Symptoms

Running the integration test suite produces:

```
AttributeError: 'DashboardAPI' object has no attribute 'get_max_id'
```

The failing code is in `tests/test_integration.py`, inside a test that validates the dashboard API routes via a live server and proxy:

```python
# Lines 347-351 — BROKEN (calls removed methods)
max_id = api.get_max_id()
assert max_id >= 3

since = api.get_requests_since(max_id - 1)
assert len(since) >= 1
```

These two blocks reference methods that no longer exist on `DashboardAPI` after the SSE removal. The rest of the same test function (lines 339–346 and 353–356) works fine because `get_requests()`, `get_request()`, and `get_all_filtered()` were not removed.

## What Didn't Work

The SSE removal plan (`docs/plans/2026-07-13-003-fix-remove-sse-from-dashboard-plan.md`) listed the test files to update, but only called out `tests/test_dashboard.py`. The integration test file `tests/test_integration.py` was not included in the plan's change list, so it was not touched during the refactor. The CI pipeline at the time may have only run unit tests, masking the integration test failure.

## Solution

Remove the four broken lines (347–351) from the proxy-routing integration test in `tests/test_integration.py`. The `get_max_id()` and `get_requests_since()` assertions tested SSE-specific functionality that no longer exists. The remaining assertions in the same test — `get_requests()`, `get_request()`, and `get_all_filtered()` — continue to validate the dashboard API's core functionality through the proxy.

**Before** (`tests/test_integration.py`, lines 339–356):

```python
            result = api.get_requests(limit=10)
            assert result["total"] == 3
            assert len(result["data"]) == 3

            detail = api.get_request(result["data"][0]["id"])
            assert detail is not None
            assert detail["method"] == "GET"

            max_id = api.get_max_id()          # <-- AttributeError
            assert max_id >= 3

            since = api.get_requests_since(max_id - 1)  # <-- AttributeError
            assert len(since) >= 1

            filtered = api.get_all_filtered(method="GET")
            assert len(filtered) == 3

            api.close()
```

**After** (`tests/test_integration.py`):

```python
            result = api.get_requests(limit=10)
            assert result["total"] == 3
            assert len(result["data"]) == 3

            detail = api.get_request(result["data"][0]["id"])
            assert detail is not None
            assert detail["method"] == "GET"

            filtered = api.get_all_filtered(method="GET")
            assert len(filtered) == 3

            api.close()
```

## Why This Works

The `get_max_id()` and `get_requests_since()` methods existed solely to support the SSE polling loop — no other code path in the application used them. After the SSE removal, these methods are gone from the `DashboardAPI`, `StorageBackend`, `DuckDBStorage`, and `SQLiteStorage` classes. Calling them from a test is guaranteed to fail.

Removing the two assertion blocks eliminates the only remaining references to these deleted methods. The test still exercises the important integration path: starting a live server, connecting through the proxy, and verifying that `get_requests()`, `get_request()`, and `get_all_filtered()` all return correct data. The SSE-specific assertions had no value after the feature was removed.

## Prevention

- **Search the entire codebase before deleting methods.** When removing a public method from a class, grep for all call sites — including test files outside the immediate feature directory (e.g., `tests/test_integration.py` vs. `tests/test_dashboard.py`).
- **Run the full test suite (unit + integration) before merging refactors.** The CI pipeline should include integration tests so that broken references surface immediately, not when someone manually runs the full suite later.
- **Use static analysis.** Tools like `ruff`, `mypy`, or IDE-based "find all references" catch dead code and missing attributes at edit time. A `mypy` strict check on the test files would have flagged the `AttributeError` before merge.
- **When a plan lists files to change, explicitly search for additional callers.** The SSE removal plan listed 9 source files to modify but missed `test_integration.py`. Plans should include a grep-based verification step: `grep -r "get_max_id\|get_requests_since" --include="*.py"` to confirm no stale references remain.

## Related

- `docs/solutions/performance-issues/remove-sse-polling-db-pressure.md` — the SSE removal fix that caused this test breakage (parent fix)
- `docs/solutions/architecture-patterns/dashboard-render-delegation-pattern.md` — related dashboard architecture decision
