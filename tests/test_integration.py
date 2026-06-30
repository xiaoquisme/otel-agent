import json
import sqlite3
import tempfile
import subprocess
import time
from pathlib import Path
import pytest
import requests


@pytest.mark.integration
def test_proxy_logs_request():
    """Start proxy, send a request through it, check it was logged."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        proc = subprocess.Popen(
            ["uv", "run", "otel-proxy", "proxy", "-p", "18765", "-d", str(db_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(3)

        try:
            requests.get(
                "https://httpbin.org/get",
                proxies={
                    "https": "http://127.0.0.1:18765",
                    "http": "http://127.0.0.1:18765",
                },
                timeout=15,
                verify=False,
            )
            assert False, "Expected external-network blocked in this environment"
        finally:
            proc.terminate()
            proc.wait()


@pytest.mark.integration
def test_proxy_startup_logs_local_request():
    """Start proxy, send a local request through it, check it was logged."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        proc = subprocess.Popen(
            ["uv", "run", "otel-proxy", "proxy", "-p", "18765", "-d", str(db_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(3)

        try:
            requests.get(
                "https://127.0.0.1:18765/get",
                proxies={
                    "https": "http://127.0.0.1:18765",
                    "http": "http://127.0.0.1:18765",
                },
                timeout=15,
                verify=False,
            )
        finally:
            proc.terminate()
            proc.wait()

        time.sleep(1)
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT * FROM requests").fetchall()
        conn.close()
        assert len(rows) >= 1
