"""Tests for the OpenRouter catalog backfill source (model capabilities).

Every test here stubs the fetcher: none of them may reach the network. The
catalog is exercised through ModelCapabilitiesCatalog instances with injected
fetchers, so the tests are deterministic and count exactly one HTTP fetch
where the design calls for one (KTD1/R6).
"""

import threading
import time

from otel_agent import model_capabilities
from otel_agent.model_capabilities import (
    CAPABILITY_FIELDS,
    ModelCapabilitiesCatalog,
    _build_indexes,
    _normalize_key,
    upstream_passthrough,
)


# ----------------------------------------------------------------------
# Fixtures / helpers
# ----------------------------------------------------------------------

def _entry(entry_id, *, context_length=128000, max_output_tokens=8192,
           input_modalities=("text", "image"), output_modalities=("text",),
           drop_top_provider=False):
    """An OpenRouter-shaped catalog entry with defaults the tests can vary.

    Keyword names mirror _caps() so tests can splat one into the other.
    """
    if entry_id is None:
        entry = {}
    else:
        entry = {"id": entry_id}
    if context_length is not None:
        entry["context_length"] = context_length
    if not drop_top_provider:
        entry["top_provider"] = {"max_completion_tokens": max_output_tokens}
    if max_output_tokens is not None and drop_top_provider:
        entry["max_completion_tokens"] = max_output_tokens
    entry["architecture"] = {
        "input_modalities": list(input_modalities),
        "output_modalities": list(output_modalities),
    }
    return entry


def _payload(*entries):
    return {"data": list(entries)}


def _caps(context_length=128000, max_output=8192,
          input_modalities=("text", "image"), output_modalities=("text",)):
    return {
        "context_length": context_length,
        "max_output_tokens": max_output,
        "input_modalities": list(input_modalities),
        "output_modalities": list(output_modalities),
    }


class _Fetcher:
    """A fetcher that records calls, can block, and can fail.

    *gate_calls* names the 1-based call numbers that block on *gate*; None
    gates every call.
    """

    def __init__(self, payloads=None, exc=None, gate=None, gate_calls=None):
        # payloads: list of answers, one per call (last one repeats).
        self.payloads = list(payloads) if payloads is not None else []
        self.exc = exc
        self.gate = gate
        self.gate_calls = gate_calls
        self.calls = 0
        self.started = threading.Event()
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.calls += 1
            call_no = self.calls
            index = min(self.calls - 1, len(self.payloads) - 1) if self.payloads else None
        self.started.set()
        if self.gate is not None and (self.gate_calls is None or call_no in self.gate_calls):
            assert self.gate.wait(5), "test gate was never released"
        if self.exc is not None:
            raise self.exc
        if index is None:
            return None
        return self.payloads[index]


def _catalog(fetcher, **kwargs):
    return ModelCapabilitiesCatalog(fetcher=fetcher, **kwargs)


def _prime(cat):
    """Cold-start prefetch + wait, exactly like process start (KTD1)."""
    cat.warm_up()
    cat.wait_for_refresh()


# ----------------------------------------------------------------------
# KTD2 matching: normalization, two-level lookup, collisions (AE2)
# ----------------------------------------------------------------------

def test_hit_by_normalized_id_returns_full_capability():
    """AE2: catalog has xiaomi/mimo-v2.5; query xiaomi/mimo-v-2.5 hits
    through the version-separator fold and returns the full capability."""
    fetcher = _Fetcher([_payload(_entry("xiaomi/mimo-v2.5", **_caps(
        context_length=200000, max_output=32768,
        input_modalities=("text", "image", "video", "audio"),
        output_modalities=("text",),
    )))])
    cat = _catalog(fetcher)
    _prime(cat)

    assert cat.lookup("xiaomi/mimo-v-2.5") == {
        "context_length": 200000,
        "max_output_tokens": 32768,
        "input_modalities": ["text", "image", "video", "audio"],
        "output_modalities": ["text"],
    }
    assert fetcher.calls == 1


def test_raw_id_level_matches_across_vendor_prefix():
    """Two-level lookup, level 1: the raw id matches even when our provider
    prefix is not the OpenRouter vendor (kimi vs moonshotai)."""
    fetcher = _Fetcher([_payload(_entry("moonshotai/kimi-k3", **_caps(context_length=262144)))])
    cat = _catalog(fetcher)
    _prime(cat)

    assert cat.lookup("kimi/kimi-k3") == _caps(context_length=262144)
    assert cat.lookup("kimi-k3") == _caps(context_length=262144)


def test_full_entry_id_disambiguates_when_raw_ids_collide():
    """Two-level lookup, level 2: when the raw id is ambiguous the full entry
    id still answers; an ambiguous bare raw id answers nothing (宁缺勿错)."""
    fetcher = _Fetcher([_payload(
        _entry("xiaomi/mimo-v2.5", **_caps(context_length=111111)),
        _entry("moonshotai/mimo-v2.5", **_caps(context_length=222222)),
    )])
    cat = _catalog(fetcher)
    _prime(cat)

    assert cat.lookup("xiaomi/mimo-v-2.5")["context_length"] == 111111
    assert cat.lookup("moonshotai/mimo-v2.5")["context_length"] == 222222
    assert cat.lookup("mimo-v-2.5") == {}


def test_vendor_alias_and_case_are_normalized():
    fetcher = _Fetcher([_payload(_entry("x-ai/grok-4.6", **_caps(context_length=256000)))])
    cat = _catalog(fetcher)
    _prime(cat)

    expected = _caps(context_length=256000)
    assert cat.lookup("x-ai/grok-4.6") == expected
    assert cat.lookup("xai/grok-4.6") == expected
    assert cat.lookup("X-AI/GROK-4.6") == expected
    assert cat.lookup("Xai/Grok-4.6") == expected


def test_variant_suffix_is_never_stripped():
    """KTD2: `:batch` / `:free` stay part of the id — OpenRouter lists them as
    independent entries, and stripping would collide the two onto one key."""
    fetcher = _Fetcher([_payload(
        _entry("moonshotai/kimi-k3", **_caps(context_length=100000, max_output=1000)),
        _entry("moonshotai/kimi-k3:batch", **_caps(context_length=200000, max_output=2000)),
    )])
    cat = _catalog(fetcher)
    _prime(cat)

    assert cat.lookup("moonshotai/kimi-k3")["context_length"] == 100000
    assert cat.lookup("moonshotai/kimi-k3:batch")["context_length"] == 200000
    assert cat.lookup("moonshotai/kimi-k3:batch")["max_output_tokens"] == 2000
    assert cat.lookup("moonshotai/kimi-k3:free") == {}


def test_key_collision_omits_the_whole_key():
    """Two entries normalizing onto one key: neither value is served."""
    fetcher = _Fetcher([_payload(
        _entry("x-ai/grok-4.6", **_caps(context_length=111111)),
        _entry("xai/grok-4.6", **_caps(context_length=222222)),
    )])
    cat = _catalog(fetcher)
    _prime(cat)

    assert cat.lookup("x-ai/grok-4.6") == {}
    assert cat.lookup("xai/grok-4.6") == {}
    assert cat.lookup("grok-4.6") == {}


def test_normalization_helpers():
    assert _normalize_key("X-AI/Grok-4.6") == "x-ai/grok-4.6"
    assert _normalize_key("xiaomi/MIMO-V-2.5") == "xiaomi/mimo-v2.5"
    assert _normalize_key("mimo-v-2.5:batch") == "mimo-v2.5:batch"


# ----------------------------------------------------------------------
# AE3: miss → empty, never a near model's value, logged internally
# ----------------------------------------------------------------------

def test_miss_returns_empty_and_logs_the_id(caplog):
    fetcher = _Fetcher([_payload(_entry("xiaomi/mimo-v2.5"))])
    cat = _catalog(fetcher)
    _prime(cat)

    with caplog.at_level("INFO", logger="otel_agent.model_capabilities"):
        assert cat.lookup("cursor/composer-2.5-sidecar") == {}
        # The miss is logged once per id, not once per lookup.
        assert cat.lookup("cursor/composer-2.5-sidecar") == {}

    assert sum("cursor/composer-2.5-sidecar" in r.message for r in caplog.records) == 1
    assert fetcher.calls == 1


def test_hit_with_no_valid_fields_is_not_a_miss(caplog):
    """A matched entry with no usable fields answers {} but is not a miss."""
    fetcher = _Fetcher([_payload({"id": "vendor/blank"})])
    cat = _catalog(fetcher)
    _prime(cat)

    with caplog.at_level("INFO", logger="otel_agent.model_capabilities"):
        assert cat.lookup("vendor/blank") == {}

    assert not [r for r in caplog.records if "vendor/blank" in r.message]


# ----------------------------------------------------------------------
# R6: whole catalog once — hit lookups do no HTTP; single-flight
# ----------------------------------------------------------------------

def test_many_lookups_trigger_exactly_one_fetch():
    fetcher = _Fetcher([_payload(_entry("xiaomi/mimo-v2.5"))])
    cat = _catalog(fetcher)
    _prime(cat)
    assert fetcher.calls == 1

    for i in range(50):
        cat.lookup(f"some/model-{i}")
    cat.lookup("xiaomi/mimo-v-2.5")
    assert fetcher.calls == 1


def test_concurrent_lookups_are_single_flight_and_non_blocking():
    gate = threading.Event()
    fetcher = _Fetcher([_payload(_entry("xiaomi/mimo-v2.5"))], gate=gate)
    cat = _catalog(fetcher)

    results = []
    results_lock = threading.Lock()

    def worker(i):
        value = cat.lookup(f"model-{i}")
        with results_lock:
            results.append(value)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    # All eight lookups answered while the single fetch was still in the air:
    # the request path never waits on the network (KTD1), and eight triggers
    # collapsed to one fetch (single-flight).
    assert len(results) == 8
    assert results == [{}] * 8
    assert fetcher.started.is_set()
    assert fetcher.calls == 1

    gate.set()
    cat.wait_for_refresh()
    assert fetcher.calls == 1


def test_stale_lookup_answers_old_table_without_waiting_for_refresh():
    gate = threading.Event()
    fetcher = _Fetcher(
        [_payload(_entry("xiaomi/mimo-v2.5", **_caps(context_length=100000))),
         _payload(_entry("xiaomi/mimo-v2.5", **_caps(context_length=200000)))],
        gate=gate,
        gate_calls={2},  # only the revalidation fetch blocks
    )
    cat = _catalog(fetcher, ttl=0.05)
    _prime(cat)
    assert cat.lookup("xiaomi/mimo-v-2.5")["context_length"] == 100000

    time.sleep(0.06)  # expire the TTL -> stale-while-revalidate

    # The stale answer comes back immediately, with the refresh gated shut.
    assert cat.lookup("xiaomi/mimo-v-2.5")["context_length"] == 100000
    assert fetcher.started.is_set()

    gate.set()
    cat.wait_for_refresh()
    assert cat.lookup("xiaomi/mimo-v-2.5")["context_length"] == 200000
    assert fetcher.calls == 2


# ----------------------------------------------------------------------
# AE4 / R8: fetch failure paths
# ----------------------------------------------------------------------

def test_fetch_failure_with_stale_cache_keeps_serving_it():
    fetcher = _Fetcher(
        [_payload(_entry("xiaomi/mimo-v2.5", **_caps(context_length=100000))),
         None],
    )
    cat = _catalog(fetcher, ttl=0.05)
    _prime(cat)

    time.sleep(0.06)  # TTL expired -> the next lookup triggers a refetch
    assert cat.lookup("xiaomi/mimo-v-2.5")["context_length"] == 100000
    cat.wait_for_refresh()

    # The refresh failed: the stale table keeps serving (stale-on-error).
    assert cat.lookup("xiaomi/mimo-v-2.5")["context_length"] == 100000
    assert cat.state() == "stale"
    assert fetcher.calls == 2


def test_fetch_failure_with_no_cache_returns_empty_and_cools_down():
    fetcher = _Fetcher([], exc=RuntimeError("unreachable"))
    cat = _catalog(fetcher)

    assert cat.lookup("xiaomi/mimo-v-2.5") == {}
    cat.wait_for_refresh()
    assert cat.state() == "failed"

    # Failure cooldown: further lookups answer empty without re-fetching.
    for i in range(5):
        assert cat.lookup(f"model-{i}") == {}
    assert fetcher.calls == 1


def test_over_age_cache_is_treated_as_absent():
    fetcher = _Fetcher([_payload(_entry("xiaomi/mimo-v2.5", **_caps(context_length=100000))), None])
    cat = _catalog(fetcher)
    _prime(cat)
    assert cat.lookup("xiaomi/mimo-v-2.5")["context_length"] == 100000

    # Age the table past the 7-day ceiling: stale-on-error stops applying.
    cat._fetched_at = time.time() - (cat._max_age + 60)

    assert cat.lookup("xiaomi/mimo-v-2.5") == {}
    cat.wait_for_refresh()
    assert cat.lookup("xiaomi/mimo-v-2.5") == {}
    assert cat.state() == "failed"


def test_failure_cooldown_expires_and_allows_a_retry():
    fetcher = _Fetcher([], exc=RuntimeError("unreachable"))
    cat = _catalog(fetcher, failure_cooldown=0.05)
    cat.lookup("m")
    cat.wait_for_refresh()
    assert fetcher.calls == 1

    time.sleep(0.06)
    cat.lookup("m")
    cat.wait_for_refresh()
    assert fetcher.calls == 2


# ----------------------------------------------------------------------
# KTD4 ingest validation: field shapes, drops, malformed payloads
# ----------------------------------------------------------------------

def test_entry_without_top_provider_max_completion_tokens_keeps_the_rest():
    """The 7/458 live case: missing max_completion_tokens costs exactly one
    field, the rest of the entry is served."""
    fetcher = _Fetcher([_payload(_entry("typesafe/jev-router", drop_top_provider=True,
                                       context_length=200000,
                                       input_modalities=("text",),
                                       output_modalities=("text",)))])
    cat = _catalog(fetcher)
    _prime(cat)

    cap = cat.lookup("typesafe/jev-router")
    assert cap == {
        "context_length": 200000,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
    }
    assert "max_output_tokens" not in cap


def test_invalid_field_values_are_dropped_not_served():
    entry = {
        "id": "vendor/bad-fields",
        "context_length": "big",
        "top_provider": {"max_completion_tokens": -5},
        "architecture": {"input_modalities": "text", "output_modalities": [1, 2]},
    }
    entry2 = {
        "id": "vendor/bad-fields-2",
        "context_length": True,
        "top_provider": {"max_completion_tokens": 2**62},
        "architecture": {"input_modalities": ["text", 7], "output_modalities": None},
    }
    fetcher = _Fetcher([_payload(entry, entry2)])
    cat = _catalog(fetcher)
    _prime(cat)

    assert cat.lookup("vendor/bad-fields") == {}
    assert cat.lookup("vendor/bad-fields-2") == {}


def test_valid_sibling_fields_survive_a_bad_field():
    fetcher = _Fetcher([_payload({
        "id": "vendor/mixed",
        "context_length": -1,
        "top_provider": {"max_completion_tokens": 4096},
        "architecture": {"input_modalities": ["text"]},
    })])
    cat = _catalog(fetcher)
    _prime(cat)

    assert cat.lookup("vendor/mixed") == {
        "max_output_tokens": 4096,
        "input_modalities": ["text"],
    }


def test_entries_without_a_usable_id_are_dropped():
    payload = _payload(
        {"context_length": 1000},
        {"id": ""},
        {"id": "   "},
        {"id": 42},
        "not-a-dict",
        _entry("vendor/kept"),
    )
    fetcher = _Fetcher([payload])
    cat = _catalog(fetcher)
    _prime(cat)

    assert cat.lookup("vendor/kept")["context_length"] == 128000
    assert cat.lookup("42") == {}


def test_malformed_payload_is_a_failure_not_an_error():
    for bad in ({"data": "nope"}, [], "garbage", {"data": {"id": "x"}}, None):
        fetcher = _Fetcher([bad])
        cat = _catalog(fetcher)
        assert cat.lookup("vendor/anything") == {}
        cat.wait_for_refresh()
        assert cat.state() == "failed"


def test_empty_catalog_is_a_successful_empty_answer():
    fetcher = _Fetcher([{"data": []}])
    cat = _catalog(fetcher)
    _prime(cat)

    assert cat.lookup("xiaomi/mimo-v-2.5") == {}
    assert cat.state() == "fresh"
    assert fetcher.calls == 1


def test_build_indexes_shape():
    built = _build_indexes(_payload(_entry("xiaomi/mimo-v2.5")))
    assert built is not None
    raw_index, full_index = built
    assert raw_index["mimo-v2.5"]["context_length"] == 128000
    assert full_index["xiaomi/mimo-v2.5"]["context_length"] == 128000


def test_lookup_returns_copies_not_shared_state():
    fetcher = _Fetcher([_payload(_entry("xiaomi/mimo-v2.5"))])
    cat = _catalog(fetcher)
    _prime(cat)

    first = cat.lookup("xiaomi/mimo-v-2.5")
    first["context_length"] = -1
    assert cat.lookup("xiaomi/mimo-v-2.5")["context_length"] == 128000


# ----------------------------------------------------------------------
# R5 upstream passthrough whitelist (shape validation shared with ingest)
# ----------------------------------------------------------------------

def test_upstream_passthrough_whitelist_is_name_and_type_exact():
    entry = {
        "context_length": 200000,
        "max_output_tokens": 32768,
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        # Near-synonyms must NOT be mapped (R5).
        "max_tokens": 999,
        "context_window": 12345,
        "max_completion_tokens": 777,
    }
    assert upstream_passthrough(entry) == {
        "context_length": 200000,
        "max_output_tokens": 32768,
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
    }


def test_upstream_passthrough_drops_wrong_types_and_absent_fields():
    assert upstream_passthrough({}) == {}
    assert upstream_passthrough({
        "context_length": 0,
        "max_output_tokens": True,
        "input_modalities": "text",
        "output_modalities": ["text", 3],
    }) == {}
    assert upstream_passthrough({"context_length": None, "max_output_tokens": 10}) == {
        "max_output_tokens": 10,
    }


def test_capability_fields_are_the_documented_four():
    assert CAPABILITY_FIELDS == (
        "context_length",
        "max_output_tokens",
        "input_modalities",
        "output_modalities",
    )


# ----------------------------------------------------------------------
# Module API: process-wide catalog wiring
# ----------------------------------------------------------------------

def test_module_lookup_and_warm_up_delegate_to_the_process_catalog(monkeypatch):
    fetcher = _Fetcher([_payload(_entry("xiaomi/mimo-v2.5", **_caps(context_length=333333)))])
    cat = ModelCapabilitiesCatalog(fetcher=fetcher)
    monkeypatch.setattr(model_capabilities, "_catalog", cat)

    model_capabilities.warm_up()
    cat.wait_for_refresh()

    assert model_capabilities.lookup("xiaomi/mimo-v-2.5")["context_length"] == 333333
    assert model_capabilities.lookup("unknown/model") == {}
    assert fetcher.calls == 1
