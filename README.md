# otel-agent — LLM API Gateway

[![Docker image](https://github.com/xiaoquisme/otel-agent/actions/workflows/docker-image.yml/badge.svg)](https://github.com/xiaoquisme/otel-agent/actions/workflows/docker-image.yml)

OpenAI/Anthropic-compatible API gateway — chat completions, messages, the Responses API, and images — with model-name-based provider routing and telemetry logging.

## Install

```bash
# Run without installing
uvx --from git+https://github.com/xiaoquisme/otel-agent.git otel-agent --version

# Install globally
uv tool install git+https://github.com/xiaoquisme/otel-agent.git

# pip fallback
pip install git+https://github.com/xiaoquisme/otel-agent.git
```

Prefer containers? See [Docker](#docker) — including prebuilt images from CI.

## Docker

Build and run the gateway as a container (dashboard included):

```bash
# Build
docker build -t otel-agent .

# Run — state persists in a named volume
docker run -d --name otel-agent \
  -p 45638:45638 \
  -v otel-agent-data:/home/otel/.otel-agent \
  otel-agent
```

Or with Compose:

```bash
docker compose up -d --build
```

Details:

- On first start the entrypoint seeds `/home/otel/.otel-agent/config.yaml` with the default template. To configure providers, mount your own config over it:

  ```bash
  docker run -d --name otel-agent \
    -p 45638:45638 \
    -v otel-agent-data:/home/otel/.otel-agent \
    -v "$PWD/config.yaml":/home/otel/.otel-agent/config.yaml:ro \
    otel-agent
  ```

- All state (`config.yaml`, `telemetry.sqlite`, `auth.json`, logs) lives in `/home/otel/.otel-agent` — keep a volume there so it survives image updates.
- The process runs as non-root user `otel` (uid 10001). When bind-mounting a host directory for state, make it writable for uid 10001.
- The gateway binds `0.0.0.0:45638` and serves the dashboard at `http://localhost:45638`.
- The image `HEALTHCHECK` probes `/health` on `OTEL_AGENT_PORT` (default `45638`). If you change the listen port with `-p`, set `OTEL_AGENT_PORT` to match.
- OAuth sign-in works headless: `docker exec -it otel-agent otel-agent auth login --no-browser`.

### Prebuilt image from CI

Every push to `main`, tag `v*`, PR, and manual dispatch runs `.github/workflows/docker-image.yml`: it builds the image from the repo Dockerfile, smoke-tests `/health` against a running container, and uploads `otel-agent-<sha>.tar.gz` as the `otel-agent-image` workflow artifact (kept 30 days). A green run always has a downloadable image — the job fails when the tarball is missing.

Download it from the run page (**Actions → Docker image → latest run → Artifacts**) or with the CLI:

```bash
# Most recent run on the current branch
gh run download "$(gh run list --workflow 'Docker image' --limit 1 --json databaseId --jq '.[0].databaseId')" \
  --name otel-agent-image --dir dist

# Load it — the image appears as otel-agent:<sha>
docker load -i dist/otel-agent-<sha>.tar.gz
```

The tarball is `linux/amd64`, ~55 MB compressed. The same image builds locally with `docker build -t otel-agent .`.

## Quick Start

```bash
# 1. Create config
otel-agent init

# 2. Edit config to add your API keys
otel-agent config edit

# 3. Start gateway (runs in background)
otel-agent proxy

# 4. Send requests with model-name routing
curl http://localhost:45638/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-4o","messages":[{"role":"user","content":"hi"}]}'
```

## How It Works

The gateway routes requests based on the **model name prefix**:

| Model String | Routes To |
|---|---|
| `openai/gpt-5.4` | OpenAI provider |
| `openrouter/openai/gpt-5.4` | OpenRouter provider (model: `openai/gpt-5.4`) |
| `xiaomi/mimo-v-2.5` | Xiaomi provider |
| `anthropic/claude-sonnet-4` | Anthropic provider |
| `xai/grok-4.6` | xAI / SuperGrok |

The first segment before `/` is always the **provider name** (looked up in config).
Everything after the first `/` is the **upstream model name** forwarded to that provider.

## Commands

```
otel-agent --version          Print version
otel-agent init               Create default config file
otel-agent proxy              Start gateway in background
otel-agent proxy stop         Stop the running gateway
otel-agent proxy restart      Restart the gateway
otel-agent proxy status       Check if gateway is running
otel-agent proxy logs         View gateway log output
otel-agent proxy --foreground Run in foreground (blocking)
otel-agent routes             Display provider routing table
otel-agent dashboard          Offline dashboard (only if proxy is stopped)
otel-agent dashboard stop     Stop the standalone dashboard
otel-agent dashboard status   Check if standalone dashboard is running
otel-agent dashboard logs     View standalone dashboard logs
otel-agent dashboard --foreground  Run standalone dashboard in foreground
otel-agent view               View logged requests (CLI)
otel-agent config path|show|edit  Manage configuration
otel-agent auth status          Show xAI / Codex login status
otel-agent auth login           SuperGrok / xAI device-code login
otel-agent auth login-codex     Codex (ChatGPT) device-code login
otel-agent auth import-xai      Adopt a Hermes / Grok CLI grant
otel-agent auth import-codex    Adopt a codex CLI grant
otel-agent auth --no-browser    Print the login URL instead of opening a browser
otel-agent doctor             Check installation health
```

## Web Dashboard

The gateway already serves the dashboard. After `otel-agent proxy`:

```bash
open http://localhost:45638
```

`otel-agent dashboard` starts a standalone viewer only when the proxy is stopped (historical / offline reads). If the proxy is running, the command prints the proxy URL and exits instead of occupying :9090.

Features:
- Request ledger with timestamp, method, URL, status, and latency
- Timeline overview with a latency bar per request (click to open)
- Text search and method/status filters (`/` focuses the search box)
- Request detail in its own window: full request/response bodies, LLM message trajectory, and a rendered message viewer
- Download a request as JSON
- Token usage view — today / week / month totals and per-model breakdown (refreshes every 30s)
- CSV/JSON export of the request log (`GET /api/export?format=csv|json`)

## API Endpoints

The gateway exposes OpenAI-compatible, Anthropic-compatible, and OpenAI Responses endpoints:

| Endpoint | Format | Description |
|---|---|---|
| `POST /v1/chat/completions` | OpenAI | Chat completions (streaming supported) |
| `POST /v1/messages` | Anthropic | Messages (streaming supported) |
| `POST /v1/responses` | OpenAI Responses | Responses API (streaming supported) |
| `POST /v1/images/generations` | OpenAI | Image generation |
| `POST /v1/images/edits` | OpenAI | Image edit (multipart: `image`, optional `mask`, `prompt`) |
| `GET /v1/models` | OpenAI | List all available models |
| `GET /health` | — | Health check |

**Cross-format conversion**: If you send an Anthropic-format request to `/v1/messages` but the target provider uses OpenAI format (or vice versa), the gateway automatically converts the request and response formats.

**Responses API**: `POST /v1/responses` behaves in three ways depending on the target provider:

- **Responses-only providers** (`auth: codex-oauth`) are passed straight through. The gateway forces `stream: true` and `store: false` upstream, adds `include: ["reasoning.encrypted_content"]`, and strips `temperature` and `max_output_tokens` (the upstream rejects them). A client that omits `stream` still gets one JSON object back — the upstream stream is folded into a single response. `previous_response_id` is refused with a 400 because the upstream keeps no server-side state; send the whole conversation in `input` instead.
- **Other OpenAI-format providers** are translated to chat completions and the reply is translated back into Responses shape (streaming and non-streaming), so Responses-only clients keep working against any chat-completions upstream.
- **Anthropic-format providers** return 400 — there is no translation path.

**Images**: `POST /v1/images/generations` and `POST /v1/images/edits` work with OpenAI-format providers; Anthropic-format providers return 400. Image content parts in chat messages pass through to the upstream unchanged, so vision requests work as well.

### Model capability metadata

Each `GET /v1/models` entry carries four optional fields alongside the core `id`/`object`/`created`/`owned_by`:

| Field | Type | Meaning |
|---|---|---|
| `context_length` | integer | Total context window length in tokens |
| `max_output_tokens` | integer | Maximum output tokens per response |
| `input_modalities` | string[] | Accepted inputs (`text`, `image`, `file`, `video`, `audio`; unknown values pass through) |
| `output_modalities` | string[] | Produced outputs (`text`, `image`, `audio`; unknown values pass through) |

A field appears only when its value is known and is omitted as a whole otherwise — never `0`, never `null`. Values are sourced per field: what the upstream catalog itself provides passes through (same name, right type), anything else is backfilled from the OpenRouter public model catalog, and anything still unknown is left out. The backfill is fetched in the background at most once a day (whole catalog, no per-model requests); when OpenRouter is unreachable the previous values keep serving for up to 7 days, and `/v1/models` neither fails nor slows down because of it.

This is zero-config on purpose: there is **no config entry for declaring capability metadata** — the fields come from the sources above or are omitted. Note also that the response field `max_output_tokens` is model metadata, not the same thing as the request parameter `max_output_tokens` accepted by `/v1/responses` (which caps a single completion).

## Config File

`~/.otel-agent/config.yaml`:

```yaml
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-proj-key1
    api_format: openai

  - name: openrouter
    base_url: https://openrouter.ai/api/v1
    api_key: sk-or-key1
    api_format: openai

  - name: xiaomi
    base_url: https://api.xiaomi.com/v1
    api_key: sk-xiaomi-key1
    api_format: openai

  - name: anthropic
    base_url: https://api.anthropic.com
    api_key: sk-ant-key1
    api_format: anthropic
```

Each provider needs:
- `name`: routing key (used as model name prefix)
- `base_url`: upstream API base URL
- `api_key`: authentication key (omit when using a subscription `auth` mode)
- `api_format`: `openai` or `anthropic` (default: `openai`)
- `auth`: optional subscription mode — `xai-oauth` for SuperGrok, `codex-oauth` for a ChatGPT/Codex subscription (both leave `api_key` empty)
- `models`: optional. Declares the models this provider serves, so `/v1/models` lists them without calling upstream
- `models_from`: optional. Names a catalog source to read the models from instead, e.g. `codex-cli`

### Declared models

An upstream that publishes no catalog can be declared on the provider row instead. The Codex subscription endpoint returns an empty list even with a valid credential, so without a declaration a `codex` provider contributes no models at all:

```yaml
providers:
  - name: codex
    base_url: https://chatgpt.com/backend-api/codex
    auth: codex-oauth
    api_format: openai
    models:
      - gpt-5.6-sol
```

A declared id is called as `codex/gpt-5.6-sol`, like any other model, and is listed without a credential being resolved. Omit the field and the provider is discovered from its upstream as before — `otel-agent` never assumes a model list of its own.

### Models from a vendor CLI

The Codex subscription endpoint publishes no catalog — it answers `{"models": []}` even with a valid credential — but the installed `codex` CLI knows the real list (`codex debug models`). Name that source and the catalog is read from it every time, so there is still no model list in this repo:

```yaml
providers:
  - name: codex
    base_url: https://chatgpt.com/backend-api/codex
    auth: codex-oauth
    api_format: openai
    models_from: codex-cli
```

`codex/gpt-6-astra` and the rest are then discoverable from `GET /v1/models`, and are listed without resolving a credential. Requires the `codex` CLI on `PATH`; if it is missing, exits non-zero, or prints something other than the catalog, the provider falls back to its upstream exactly as if the field were absent. An unrecognized source name is ignored at load rather than failing the gateway.

### SuperGrok / xAI

Use a SuperGrok subscription instead of an xAI API key. You need SuperGrok itself — X Premium+ is not enough.

```bash
# Sign in (opens the browser; SSH sessions print a URL instead)
otel-agent auth login

# Already signed in with Hermes or `grok login`? Copy that grant once
otel-agent auth import-xai

# Check login
otel-agent auth status
```

Then start the gateway and call Grok like any other provider:

```bash
otel-agent proxy

curl http://localhost:45638/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"xai/grok-4.6","messages":[{"role":"user","content":"hi"}]}'
```

What this does:

- Logs you into xAI in the browser (device-code). SSH / `--no-browser` just prints the URL and code.
- Saves tokens in `~/.otel-agent/auth.json` and adds an `xai` provider to config. You do not paste an API key.
- After login, use model `xai/grok-4.6`. Tokens refresh automatically while the proxy is running.
- `import-xai` copies an existing Hermes / Grok CLI login. It does not change Hermes' files.

Do not expose the proxy on a shared network — anyone who can reach it can spend your SuperGrok quota. If a request still 403s after a successful login, the account is not entitled (or is out of quota); see https://grok.com/?_s=usage. Re-login will not fix that.

### Codex / ChatGPT subscription

Proxy a ChatGPT (Codex) subscription instead of an API key. The Codex upstream serves only the Responses API, so calls go to `POST /v1/responses` (see API Endpoints above).

```bash
# Sign in (device-code; opens the browser, or prints the URL with --no-browser / SSH)
otel-agent auth login-codex

# Already signed in with the `codex` CLI? Adopt that grant instead
otel-agent auth import-codex

# Check login
otel-agent auth status
```

What this does:

- `login-codex` mints a fresh grant chain owned by this gateway alone — no sibling CLI is read or modified. Tokens are saved in `~/.otel-agent/auth.json` and a `codex` provider is added to config; you do not paste an API key.
- `import-codex` adopts a grant already held by the `codex` CLI (its files are not modified). This is a hand-off: from then on this gateway is the chain's only writer — the sibling's sign-in goes stale, and a second writer refreshing the chain will invalidate it.
- Tokens refresh automatically while the proxy is running. Use `codex/<model>` (e.g. `codex/gpt-5.6-sol`). The endpoint publishes no model catalog, so declare `models:` or `models_from: codex-cli` as described above.
- `/v1/chat/completions` and `/v1/messages` refuse a `codex` provider with a 400 that points at `/v1/responses` — the upstream would 404 those routes anyway.

Same warning as SuperGrok: do not expose the proxy on a shared network — anyone who can reach it can spend your subscription quota.

### Cursor subscription

Cursor dashboard API keys are not an OpenAI chat-completions host (`POST https://api.cursor.com/v1/chat/completions` is 404). Point a `cursor` provider at a local OpenAI sidecar (`cursor-agent-api`) that wraps the Cursor CLI.

```yaml
providers:
  - name: cursor
    base_url: http://127.0.0.1:4646/v1
    api_key: crsr_YOUR_KEY
    api_format: openai
```

Install the CLI and sidecar once (`agent` on PATH, `npm install -g cursor-agent-api-proxy`). `otel-agent proxy start` / `stop` then starts and stops the sidecar with the gateway. `/v1/models` lists ids from `agent --list-models` (not the sidecar's stale catalog). Prefer `cursor/auto` or `cursor/composer-2.5`; OpenAI-family ids may be region-blocked.

Do not put `auth: xai-oauth` on this provider — the key is static YAML, like any other `api_key`.

## Client Usage

### OpenAI SDK

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:45638/v1", api_key="dummy")
response = client.chat.completions.create(
    model="openai/gpt-4o",  # or "xiaomi/mimo-v-2.5"
    messages=[{"role": "user", "content": "Hello!"}],
)
```

### Anthropic SDK

```python
import anthropic
client = anthropic.Anthropic(base_url="http://localhost:45638", api_key="dummy")
response = client.messages.create(
    model="anthropic/claude-sonnet-4",  # or "xiaomi/mimo-v-2.5"
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
```

### curl

```bash
# List available models
curl http://localhost:45638/v1/models

# Filter by provider
curl "http://localhost:45638/v1/models?provider=openai"

# OpenAI format
curl http://localhost:45638/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-4o",
    "messages": [{"role": "user", "content": "hi"}],
    "stream": true
  }'

# Anthropic format
curl http://localhost:45638/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-sonnet-4",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "hi"}]
  }'

# Responses API (e.g. for Codex-only clients)
curl http://localhost:45638/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-4o",
    "input": "hi"
  }'
```

## Testing

```bash
uv run pytest tests/ -v -m "not integration"
```

## License

MIT
