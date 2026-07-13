# Quickstart: Validate Dashboard Usage Metrics

## Prerequisites

- Python environment synchronized with `uv`.
- Run commands from the repository root.
- Use the source-layout import path during local test execution:

  ```sh
  export PYTHONPATH="$(pwd):$(pwd)/src"
  ```

## Automated validation

Run the deterministic project test gate:

```sh
uv run pytest -m 'not integration'
```

Expected result: all selected tests pass. The suite's network-dependent integration tests are intentionally excluded by the project's marker configuration.

Run the focused usage-metrics tests once implemented:

```sh
uv run pytest tests/test_dashboard.py tests/test_logger.py tests/test_migration.py tests/test_server.py -v
```

Expected result: coverage demonstrates normalization, schema compatibility, proxy-routed usage reads, direct offline reads, API validation, and dashboard rendering behavior.

## End-to-end dashboard scenario

1. Start the proxy with a fresh telemetry database and start the dashboard using the same configured telemetry location.
2. Send successful OpenAI-compatible and Anthropic-compatible non-streaming completion requests with known provider-reported usage and distinct model identifiers.
3. Open the dashboard in a browser.
4. Verify the total, input, and output cards equal the known aggregate for the browser's local day.
5. Verify the model table is descending by total tokens, shows per-model request counts, and includes both model identifiers without merging them.
6. Send an additional successful request with known usage. Verify the overview updates within two seconds without restarting the dashboard.
7. Send a successful response with no usable usage data. Verify totals remain unchanged and the coverage note reports one excluded request.
8. Send a streaming request whose terminal chunk reports usage. Verify its usage contributes to the overview; then send an interrupted stream without a usage event and verify it is reported as excluded rather than estimated from the preview.
9. Resize the browser to a narrow viewport. Verify cards and the model table remain readable, labels remain visible, and no value depends on color alone.
10. While the proxy is active, verify the dashboard continues to load requests and metrics without a storage-lock error. Stop the proxy and verify the dashboard's offline direct-read path can still display persisted metrics.

## Related design artifacts

- [Data model](./data-model.md)
- [Dashboard usage API contract](./contracts/dashboard-usage-api.md)
- [Research decisions](./research.md)
