---
title: Reload config when a rewrite shares the filesystem timestamp
date: 2026-10-19
category: runtime-errors
module: config
problem_type: runtime_error
component: hot_reload
severity: medium
applies_when:
  - Two config.yaml writes land in the same st_mtime tick
  - ModelCache invalidation depends on Config._mtime
tags:
  - config
  - mtime
  - hot-reload
---

# Reload config when a rewrite shares the filesystem timestamp

## Context

`Config._reload` used to return immediately when `st_mtime` was unchanged. On a filesystem whose timestamp does not move between two back-to-back writes, hot reload kept the previous providers, and `ModelCache` (which watches `Config._mtime`) kept the old catalog.

## Guidance

- Hash the file bytes. Skip parsing only when both the hash and `st_mtime` match the last load.
- Keep `Config._mtime` as the value `ModelCache` compares. When the bytes change but `st_mtime` does not, increment `_mtime` so the cache drops.
- Store the filesystem stamp separately (`_fs_mtime`) so a later real timestamp change is still noticed.

## Why This Matters

A same-tick rewrite is a normal save on a coarse clock. Treating it as "unchanged" serves the previous API keys and base URLs until something else touches the file.

## When to Apply

- Changing how config or any other hot-reloaded file decides it is stale
- Adding another cache that keys off `Config._mtime`
