#!/bin/sh
# Container entrypoint: seed a default config on first boot, then run the CLI.
set -e

if [ ! -f "$HOME/.otel-agent/config.yaml" ]; then
    otel-agent init
fi

# `docker run image proxy --foreground` or `--version` -> `otel-agent ...`.
# Anything else (`sh`, `otel-agent`, ...) is executed as-is.
case "$1" in
    proxy|init|view|config|doctor|routes|dashboard|auth|--*)
        set -- otel-agent "$@"
        ;;
esac

exec "$@"
