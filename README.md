# MultiBots v2 — Enterprise Multi-Bot Hosting Platform

> Host, supervise, monitor, and operate **all your Python bots** from a single
> Docker container with a built-in web dashboard, REST API, crash recovery,
> webhook alerts, and graceful shutdown.

[![Tests](https://img.shields.io/badge/tests-117%20passing-brightgreen)](#testing)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](#prerequisites)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)
[![Docker](https://img.shields.io/badge/docker-multi--arch-2496ed)](#docker-deployment)

---

## Table of Contents

1. [Overview](#1-overview)
2. [What's New in v2](#2-whats-new-in-v2)
3. [Architecture](#3-architecture)
4. [Quick Start (5 minutes)](#4-quick-start-5-minutes)
5. [Configuration Reference](#5-configuration-reference)
6. [Web Dashboard](#6-web-dashboard)
7. [REST API Reference](#7-rest-api-reference)
8. [Environment Variables](#8-environment-variables)
9. [Docker Deployment](#9-docker-deployment)
10. [Production Hardening](#10-production-hardening)
11. [Security Model](#11-security-model)
12. [Monitoring & Alerting](#12-monitoring--alerting)
13. [Troubleshooting](#13-troubleshooting)
14. [Testing](#14-testing)
15. [Migration Guide (v1 → v2)](#15-migration-guide-v1--v2)
16. [Contributing](#16-contributing)
17. [License](#17-license)

---

## 1. Overview

**MultiBots** runs multiple Python bots (typically Telegram bots, but any
long-running Python script works) inside a single Docker container. Each bot
runs as its own subprocess with its own environment, working directory, and
lifecycle — supervised by a single watchdog process that restarts crashed
bots, drains their logs, and reports state to a password-protected web
dashboard.

**Why one container for many bots?**
Most Telegram bots idle at <50 MB RAM. Running each in its own container
wastes 300–500 MB of overhead per bot. MultiBots lets you colocate 5–20 bots
in a single 512 MB container — cutting hosting costs by 80–95% on platforms
like Render, Heroku, Scalingo, Fly.io, or a $5 VPS.

**Who is this for?**
- Indie developers running multiple side-project bots
- Small teams that want one ops surface for several bots
- Students learning process supervision / Docker / Flask
- Anyone who has ever been paged at 3am because a free-host container slept
  and their bot stopped responding

---

## 2. What's New in v2

v2 is a **full enterprise rewrite** of v1, with **100% backward compatibility**
for the original `config.json` schema. The original 5 files / 90 lines of
Python became a 9-section modular supervisor + a separate dashboard module.

### Capability matrix

| Capability | v1.0 | v2.0 |
|---|---|---|
| Multi-bot hosting in one container | ✅ | ✅ |
| Private repo cloning | ✅ | ✅ |
| Per-bot env vars | ✅ | ✅ |
| Keep-alive pinger | ⚠️ buggy | ✅ fixed (127.0.0.1, no race) |
| Process supervision (auto-restart) | ❌ | ✅ exponential backoff |
| Max-restart cap (give up after N) | ❌ | ✅ |
| Graceful shutdown (SIGTERM/SIGINT) | ❌ orphans children | ✅ drains cleanly |
| Web dashboard (HTML) | ❌ gif only | ✅ live CPU/RAM/logs/controls |
| Password auth on dashboard | ❌ | ✅ PBKDF2 + CSRF + rate limit |
| REST API for bot control | ❌ | ✅ start/stop/restart/enable/disable |
| Per-bot metrics (CPU/RAM history) | ❌ | ✅ 5s sampling, 180pt window |
| System metrics (load/disk/swap) | ❌ | ✅ |
| Webhook crash alerts (Slack/Discord) | ❌ | ✅ |
| Structured logging w/ per-bot tagging | ❌ | ✅ |
| Config validation | ❌ crashes weirdly | ✅ fail-fast, skip-and-continue |
| Env-var overrides for every setting | ❌ | ✅ |
| Healthcheck endpoint | ❌ | ✅ `/healthz` + `/readyz` |
| Non-root Docker user | ❌ | ✅ uid 1000 |
| Multi-arch Docker image (amd64+arm64) | ❌ | ✅ |
| Hot-reload-friendly config | ❌ | ✅ |
| Test suite | ❌ | ✅ 117 tests (unit + integration + e2e) |
| Python version | 3.9 (EOL Oct 2025) | 3.11 |

### Backward compatibility promise

Any `config.json` that worked with v1 still works with v2 — no migration
required. New optional fields (`enabled`, `max_restarts`, `restart_delay_base`,
`health_url`, `args`, etc.) default to safe values when omitted. See
[§15. Migration Guide](#15-migration-guide-v1--v2).

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Docker Container                          │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              dashboard.py (Flask + gunicorn)              │  │
│  │                                                           │  │
│  │   /login ───────► PBKDF2 verify + HMAC session cookie     │  │
│  │   /            ──► HTML dashboard (auto-refresh)          │  │
│  │   /api/status ──► JSON system + bot snapshot              │  │
│  │   /api/bots/X/<action> ──► start/stop/restart/...         │  │
│  │   /healthz, /readyz ──► unauth liveness probes            │  │
│  └─────────────┬─────────────────────────────────────────────┘  │
│                │ imports                                        │
│  ┌─────────────▼─────────────────────────────────────────────┐  │
│  │                    main.py (supervisor)                   │  │
│  │                                                           │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │  │
│  │  │ ConfigLoader │  │  BotSuperv.  │  │MetricsCollector│  │  │
│  │  │  (validate)  │  │  (watchdog)  │  │   (psutil)     │  │  │
│  │  └──────────────┘  └──────┬───────┘  └────────────────┘  │  │
│  │                          │ start/stop/restart             │  │
│  │  ┌──────────────────┐    │                               │  │
│  │  │ WebhookNotifier  │◄───┤ on crash                      │  │
│  │  └──────────────────┘    │                               │  │
│  │  ┌──────────────────┐    │                               │  │
│  │  │ KeepAlivePinger  │    │                               │  │
│  │  └──────────────────┘    │                               │  │
│  │  ┌──────────────────┐    │                               │  │
│  │  │ GracefulShutdown │◄───┤ SIGTERM/SIGINT                │  │
│  │  └──────────────────┘    │                               │  │
│  └──────────────────────────┼───────────────────────────────┘  │
│                              │ subprocess.Popen                  │
│  ┌───────────────┐  ┌────────▼───────┐  ┌───────────────────┐  │
│  │  bot1/        │  │  bot2/         │  │  bot3/            │  │
│  │  └── main.py  │  │  └── bot.py    │  │  └── main.py      │  │
│  └───────────────┘  └────────────────┘  └───────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### File layout

| File | Purpose | Lines |
|---|---|---|
| `main.py` | Supervisor core (config + supervisor + metrics + hooks) | ~700 |
| `dashboard.py` | Web UI + REST API + auth | ~700 |
| `config.json` | Bot definitions (your bots) | varies |
| `run.sh` | Build-time: clone bot repos + install their deps | ~90 |
| `Dockerfile` | Image build (multi-arch, non-root, healthcheck) | ~55 |
| `requirements.txt` | MultiBots runtime deps (Flask, psutil, requests, gunicorn) | 5 |
| `tests/` | Unit + integration + e2e tests (117 tests) | ~700 |
| `scripts/` | Live smoke tests + backward-compat tests | ~250 |

### Threading model

```
Main thread ─────► dashboard.py gunicorn workers (HTTP)
                  │
                  ├─► multibots.supervisor (daemon) — watchdog loop
                  ├─► multibots.metrics     (daemon) — 5s sampler
                  ├─► multibots.pinger      (daemon) — keep-alive
                  ├─► multibots.shutdown     (signal handler)
                  └─► multibots.bot.<name>  (daemon per bot) — log drainer
```

All daemon threads die when the main thread exits; the SIGTERM handler
calls `os._exit(0)` after draining to bypass any hung subprocess.

---

## 4. Quick Start (5 minutes)

### Prerequisites

- Docker 20+ (or Python 3.9+ if running without Docker)
- A GitHub account (for cloning bot repos)
- Bot tokens (e.g. from [@BotFather](https://t.me/BotFather) for Telegram)

### Step 1 — Clone MultiBots

```bash
git clone https://github.com/maruf009sultan/MultiBots.git
cd MultiBots
```

### Step 2 — Configure your bots

Edit `config.json`:

```json
{
    "my_first_bot": {
        "source": "https://github.com/your-username/your-bot-repo.git",
        "run": "main.py",
        "env": {
            "TOKEN": "123456:ABC-DEF_your_telegram_bot_token",
            "OTHER_VAR": "value"
        },
        "enabled": true
    },
    "another_bot": {
        "source": "https://github.com/your-username/another-bot.git",
        "run": "bot.py",
        "env": {"TOKEN": "another-token"},
        "max_restarts": 10
    }
}
```

> **Each bot repo must have its own `requirements.txt`** at the root.
> MultiBots installs it automatically during the Docker build.

### Step 3 — Build and run

```bash
docker build -t multibots .
docker run -p 10000:10000 multibots
```

### Step 4 — Open the dashboard

Visit `http://localhost:10000` in your browser. On first boot, MultiBots
**auto-generates a password and prints it to the Docker logs**:

```bash
docker logs multibots 2>&1 | grep "Generated:"
# → No dashboard password configured. Generated: river-frost-42
```

Log in with that password. You'll see:
- Live CPU / memory / disk / load averages for the container
- A card per bot showing status, PID, uptime, restart count, CPU%, memory
- Start / Stop / Restart buttons for each bot
- A live supervisor log tail

---

## 5. Configuration Reference

`config.json` is the single source of truth for bot definitions. It supports
three kinds of top-level keys:

- `_dashboard` — optional dashboard settings (password, session secret)
- `_global` — optional default values inherited by every bot
- `<bot_name>` — bot definitions (any name not starting with `_`)

### Full schema

```json
{
    "_dashboard": {
        "password_hash": "pbkdf2_sha256$240000$<salt>$<hash>",
        "session_secret": "any-random-string"
    },
    "_global": {
        "max_restarts": 5,
        "restart_delay_base": 2.0
    },
    "my_bot": {
        "source": "https://github.com/user/repo.git",
        "run": "main.py",

        "env": {"TOKEN": "...", "DEBUG": "true"},
        "enabled": true,
        "max_restarts": 5,
        "restart_delay_base": 2.0,
        "health_url": "",
        "health_timeout": 5.0,
        "cwd": null,
        "python": "python3",
        "args": ["--worker-count", "4"],
        "timeout_graceful": 10.0
    }
}
```

### Field reference

#### Bot-level fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `source` | string | ✅ | — | Git URL. Supports `https://`, `http://`, `git@`, `ssh://`. For private repos, embed the token: `https://user:token@github.com/user/repo.git` |
| `run` | string | ✅ | — | Entry filename **inside the bot directory** (e.g. `main.py`). Must be a bare filename — no path separators. |
| `env` | object | ❌ | `{}` | Environment variables passed to the bot. All values coerced to strings. |
| `enabled` | bool | ❌ | `true` | If `false`, the bot is never started and shows as "disabled" in the dashboard. |
| `max_restarts` | int \| null | ❌ | inherits `_global.max_restarts` (default `5`) | Max restart attempts before giving up. `null` = inherit; `0` = never restart. |
| `restart_delay_base` | float \| null | ❌ | inherits (default `2.0`) | Base delay in seconds for exponential backoff. Actual delay = `min(base * 2^(attempt-1), restart_delay_max)`. |
| `health_url` | string | ❌ | `""` | Optional HTTP health probe URL. (Reserved for future use; not yet auto-polled.) |
| `health_timeout` | float | ❌ | `5.0` | Timeout in seconds for the health probe. |
| `cwd` | string \| null | ❌ | `<bots_dir>/<bot_name>` | Override the working directory. If absolute, used as-is; if relative, joined with `bots_dir`. |
| `python` | string | ❌ | `sys.executable` | Python interpreter to use (e.g. `python3.11`). |
| `args` | array | ❌ | `[]` | Extra command-line arguments passed after the run file. |
| `timeout_graceful` | float | ❌ | `10.0` | Seconds to wait after SIGTERM before sending SIGKILL. |

#### Reserved top-level keys

| Key | Purpose |
|---|---|
| `_dashboard.password_hash` | Pre-set the dashboard password (avoids auto-generation). Generate with: `python -c "import dashboard; print(dashboard.hash_password('yourpw'))"` |
| `_dashboard.session_secret` | Secret used to sign session cookies. If omitted, a random one is generated per process (sessions don't survive restart). |
| `_global.max_restarts` | Default `max_restarts` for bots that don't specify one. |
| `_global.restart_delay_base` | Default `restart_delay_base` for bots that don't specify one. |

### Validation rules

Bot names must match `^[A-Za-z][A-Za-z0-9_-]{0,63}$` (1–64 chars, starts
with a letter, only letters/digits/underscore/hyphen). Invalid bot names
are skipped at load time with an error log — other bots still load.

The `run` field must be a **bare filename** (no `/` or `\`, no absolute
paths). This prevents path traversal outside the bot directory.

If a single bot's config is invalid, that bot is skipped — the rest still
load. The supervisor never crashes on a single bad bot.

---

## 6. Web Dashboard

The dashboard runs on port 10000 by default (override with `MB_PORT`).
It provides:

### Pages

| Route | Auth | Description |
|---|---|---|
| `GET /` | ✅ | HTML dashboard (auto-refreshes every 30s) |
| `GET /login` | ❌ | Login form |
| `POST /login` | ❌ | Authenticate, set session cookie |
| `POST /logout` | ❌ | Clear session |
| `GET /healthz` | ❌ | Liveness probe (always 200) |
| `GET /readyz` | ❌ | Readiness probe (200 if supervisor attached, else 503) |

### Dashboard features

- **System overview panel**: CPU %, load averages (1/5/15m), core count,
  memory used/total, swap, disk %, process count, container uptime.
- **Per-bot cards**: status dot (running/crashed/stopped/restarting/disabled),
  PID, uptime, restart count, last exit code, CPU%, memory MB, last error.
- **Action buttons**: Start / Restart / Stop (with confirmation dialog).
- **Logs link**: opens a per-bot log tail in a new tab.
- **Live supervisor log**: auto-refreshing supervisor log at the bottom.
- **Color-coded bars**: green (OK), yellow (warn), red (critical) for CPU
  and memory thresholds.

### Authentication model

- **Password storage**: PBKDF2-HMAC-SHA256, 240,000 iterations, 24-byte salt.
  Format: `pbkdf2_sha256$<iter>$<salt_b64>$<hash_b64>` (Django-compatible).
- **Session**: HMAC-signed cookie, 12-hour TTL, `HttpOnly` + `SameSite=Lax`.
  Marked `Secure` when the request is over HTTPS.
- **CSRF**: every state-changing POST requires `X-CSRF-Token` header matching
  the session-issued token. Bad/missing token → 403.
- **Rate limiting**: 5 failed login attempts per minute per IP → 429.

### Auto-generated password

If no password is configured (neither env var nor `_dashboard.password_hash`),
MultiBots generates one on first boot, prints it to stdout/logs, and
persists the hash to `.multibots_dashboard_pw` next to `config.json` so
it survives restarts.

```bash
# View the auto-generated password from logs:
docker logs multibots 2>&1 | grep "Generated:"

# Or set a fixed password:
python -c "import dashboard; print(dashboard.hash_password('your-strong-pw'))"
# → pbkdf2_sha256$240000$abc...$def...
# Paste that into config.json under _dashboard.password_hash
```

---

## 7. REST API Reference

All `/api/*` endpoints require authentication (session cookie). State-changing
endpoints also require a CSRF token (the `X-CSRF-Token` header).

### Read endpoints

#### `GET /api/status`

Returns the full system + per-bot snapshot.

```json
{
    "ts": "2026-07-05T18:40:09Z",
    "version": "2.0.0",
    "system": {
        "cpu_percent": 12.3,
        "cpu_count": 4,
        "load_1": 0.45, "load_5": 0.32, "load_15": 0.28,
        "mem_total_mb": 2048.0, "mem_used_mb": 612.5, "mem_percent": 29.9,
        "swap_total_mb": 1024.0, "swap_used_mb": 0.0, "swap_percent": 0.0,
        "disk_percent": 47.2,
        "boot_time": 1783276000.0,
        "process_count": 87
    },
    "bots": [
        {
            "name": "my_bot",
            "status": "running",
            "pid": 1234,
            "uptime_s": 3600.5,
            "restart_count": 0,
            "last_exit_code": null,
            "last_error": "",
            "cpu_percent": 1.2,
            "memory_mb": 45.3,
            "history": [{"t": 1783276000.0, "cpu": 1.1, "mem": 45.0}, ...],
            "config": {
                "name": "my_bot",
                "source": "https://github.com/user/repo.git",
                "run": "main.py",
                "enabled": true,
                "max_restarts": 5,
                "has_env": true,
                "env_keys": ["TOKEN"],
                "env_masked": {"TOKEN": "1234…cdef"},
                ...
            }
        }
    ]
}
```

> **Secret masking**: env values are always masked in API responses.
> A value of length `L` is shown as `<first4>…<last4>` if `L > 8`, else
> `*` repeated `L` times. Raw values never leave the process.

#### `GET /api/bots`

Returns an array of all bot states (same shape as `bots[]` above).

#### `GET /api/bots/<name>`

Returns a single bot's state. 404 if unknown.

#### `GET /api/bots/<name>/logs?lines=200`

Returns up to 2000 lines of recent log output for the bot as `text/plain`.
Lines are tagged with the bot logger name: `[multibots.bot.<name>]`.

#### `GET /api/supervisor_log?lines=100`

Returns recent supervisor log lines (all bots + supervisor events).

#### `GET /api/metrics/history/<name>`

Returns the per-bot CPU/RAM history as a JSON array of `{t, cpu, mem}` samples
(5s interval, up to 180 points = 15 min window).

### Action endpoints

All actions are `POST` and require `X-CSRF-Token` header.

| Endpoint | Effect |
|---|---|
| `POST /api/bots/<name>/start` | Start the bot if stopped. Idempotent (no-op if already running). |
| `POST /api/bots/<name>/stop` | SIGTERM → wait `timeout_graceful` → SIGKILL if still alive. |
| `POST /api/bots/<name>/restart` | Stop then start. New PID. |
| `POST /api/bots/<name>/enable` | Set `enabled=true` and start the bot. |
| `POST /api/bots/<name>/disable` | Set `enabled=false` and stop the bot. Watchdog will not restart it. |

#### Response shape

```json
{"ok": true, "action": "restart", "bot": "my_bot"}
```

On error:

```json
{"ok": false, "error": "unknown bot"}
```

### Example: restart a bot from curl

```bash
# 1. Login (saves cookies to ./cookies.txt)
curl -c cookies.txt -X POST http://localhost:10000/login \
     -d "password=your-password"

# 2. Get CSRF token (from the dashboard HTML)
CSRF=$(curl -b cookies.txt http://localhost:10000/ | \
       grep -oP 'const csrf = "\K[^"]+')

# 3. Restart a bot
curl -b cookies.txt -X POST http://localhost:10000/api/bots/my_bot/restart \
     -H "X-CSRF-Token: $CSRF"
```

---

## 8. Environment Variables

Every setting in `DEFAULTS` (see `main.py`) can be overridden via an
environment variable with the `MB_` prefix. Env vars take precedence over
`config.json` defaults but **not** over explicit bot-level config.

| Variable | Default | Description |
|---|---|---|
| `MB_PORT` | `10000` | Dashboard HTTP port |
| `MB_HOST` | `0.0.0.0` | Dashboard bind address |
| `MB_BOTS_DIR` | `/app` | Root directory containing bot subdirectories |
| `MB_CONFIG_PATH` | `config.json` | Path to the bots config file |
| `MB_LOG_LEVEL` | `INFO` | Root log level (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |
| `MB_LOG_DIR` | `logs` | Directory for rotating log files (empty = console only) |
| `MB_LOG_MAX_BYTES` | `5242880` | Max bytes per log file before rotation |
| `MB_LOG_BACKUP_COUNT` | `5` | Number of rotated log files to keep |
| `MB_START_DELAY` | `2.0` | Seconds between bot startups (avoid fork-bomb) |
| `MB_MAX_RESTARTS` | `5` | Default max restarts before giving up |
| `MB_RESTART_DELAY_BASE` | `2.0` | Base delay for exponential backoff |
| `MB_RESTART_DELAY_MAX` | `120.0` | Cap on backoff delay |
| `MB_WATCHDOG_INTERVAL` | `10.0` | Seconds between watchdog polls |
| `MB_PING_INTERVAL` | `120.0` | Keep-alive ping interval (set high to disable) |
| `MB_PING_URL` | `http://127.0.0.1:10000/` | URL to ping (use external URL for cross-host keep-alive) |
| `MB_WEBHOOK_URL` | `""` | Slack/Discord/generic webhook URL for crash alerts |
| `MB_WEBHOOK_TIMEOUT` | `5.0` | Webhook POST timeout |
| `MB_SHUTDOWN_TIMEOUT` | `15.0` | Grace period for SIGTERM before SIGKILL |
| `MB_METRICS_HISTORY` | `180` | Number of per-bot metric samples to keep (180 × 5s = 15min) |
| `MB_DASHBOARD_ENABLED` | `true` | Set to `false` to disable the dashboard |
| `MB_DASHBOARD_PASSWORD_HASH` | `""` | Pre-set dashboard password hash |
| `MB_DASHBOARD_SESSION_SECRET` | `""` | Session signing secret (auto-generated if empty) |

---

## 9. Docker Deployment

### Local build & run

```bash
docker build -t multibots .
docker run -d --name multibots -p 10000:10000 multibots
```

### Multi-arch build (amd64 + arm64)

```bash
docker buildx create --use --name mb-builder
docker buildx build --platform linux/amd64,linux/arm64 \
       -t your-registry/multibots:latest --push .
```

### Docker Compose

```yaml
version: "3.8"
services:
  multibots:
    build: .
    ports:
      - "10000:10000"
    volumes:
      - ./config.json:/app/config.json:ro
      - ./logs:/app/logs
    environment:
      - MB_WEBHOOK_URL=https://hooks.slack.com/services/...
      - MB_DASHBOARD_PASSWORD_HASH=pbkdf2_sha256$240000$...
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:10000/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
```

### Cloud platform deployment

#### Render

1. Push this repo to GitHub.
2. New → Web Service → connect the repo.
3. **Build Command**: `docker build -t multibots .` (or leave blank — Render auto-detects Dockerfile).
4. **Start Command**: `docker run -p $PORT -e MB_PORT=$PORT multibots` (or use Render's native Docker deploy).
5. Set `MB_DASHBOARD_PASSWORD_HASH` in Render's Environment tab.
6. Exposed port: 10000 (Render auto-detects from `EXPOSE`).

#### Heroku

```bash
heroku container:push web -a your-app
heroku container:release web -a your-app
heroku config:set MB_DASHBOARD_PASSWORD_HASH=pbkdf2_sha256\$240000\$... -a your-app
```

#### Fly.io

```bash
fly launch --image multibots
fly secrets set MB_DASHBOARD_PASSWORD_HASH=pbkdf2_sha256\$240000\$...
fly deploy
```

---

## 10. Production Hardening

### Set a fixed dashboard password

```bash
# Generate the hash:
docker run --rm multibots python -c \
    "import dashboard; print(dashboard.hash_password('your-strong-password'))"

# Paste the output into config.json:
{
    "_dashboard": {
        "password_hash": "pbkdf2_sha256$240000$abc...$def..."
    }
}
```

Or via env var (preferred for CI/CD):
```bash
export MB_DASHBOARD_PASSWORD_HASH='pbkdf2_sha256$240000$abc...$def...'
```

### Set a stable session secret

Without a stable session secret, all users get logged out on every restart:
```bash
export MB_DASHBOARD_SESSION_SECRET="$(openssl rand -hex 32)"
```

### Enable crash alerts

```bash
# Slack incoming webhook:
export MB_WEBHOOK_URL='https://hooks.slack.com/services/T.../B.../...'

# Discord webhook:
export MB_WEBHOOK_URL='https://discord.com/api/webhooks/.../...'
```

Crash alerts include the bot name, exit reason, and timestamp. Webhook
delivery is best-effort — a failed webhook never blocks the supervisor.

### Run behind HTTPS

The dashboard sets `Secure` cookies automatically when the request is over
HTTPS. For termination at a reverse proxy (nginx/Caddy/Cloudflare), ensure
`X-Forwarded-Proto: https` is set so Flask sees `request.is_secure == True`.

### Resource limits

In `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '0.5'
```

MultiBots itself uses <50 MB RAM. The 512 MB limit leaves room for ~5–10
typical Telegram bots.

### Log management

```bash
# Rotate logs with 10MB × 5 files:
export MB_LOG_MAX_BYTES=10485760
export MB_LOG_BACKUP_COUNT=5
```

For Docker log drivers, the supervisor's stdout is unbuffered — `docker logs`
works without configuration.

---

## 11. Security Model

### Threat model

MultiBots assumes:
- The container runtime (Docker/host) is trusted.
- The bot source code is trusted (you wrote or reviewed it).
- The dashboard port (10000) is **not** exposed to the public internet
  without TLS + a strong password.

### Secrets handling

| Secret | Where it lives | Risk |
|---|---|---|
| Bot env vars (TOKENs) | `config.json` `env` block + bot process env | Medium — never logged, never exposed via API (masked). Filesystem access required to read. |
| GitHub token (private repos) | Embedded in `source` URL | Medium — `run.sh` suppresses URL echo. Filesystem access required to read `config.json`. |
| Dashboard password | PBKDF2 hash in config or env var | Low — only the hash is stored; brute force at 240k iterations is impractical. |
| Session secret | Env var or auto-generated | Medium — if compromised, attacker can forge session cookies until restart. |

### What MultiBots does NOT do

- ❌ It does **not** encrypt `config.json` at rest. Use filesystem encryption
  (LUKS, gocryptfs) if your threat model requires it.
- ❌ It does **not** sandbox bot subprocesses. A malicious bot can read other
  bots' env vars if it has filesystem access. Run untrusted bots in separate
  containers.
- ❌ It does **not** provide multi-user auth. The dashboard has a single
  shared password. For multi-user, put it behind OAuth Proxy / Authelia /
  Cloudflare Access.

### CSRF protection

Every state-changing API endpoint (`POST /api/bots/...`) requires an
`X-CSRF-Token` header that matches the session-issued token. The token is
embedded in the dashboard HTML as `const csrf = "..."` and rendered into
each action button's JavaScript. Browsers' `SameSite=Lax` cookie policy
provides defense-in-depth against cross-site requests.

### Rate limiting

Login attempts are throttled to 5 per minute per IP. The limiter is
in-memory (per-process); for multi-worker gunicorn deployments, each worker
tracks its own counter — effective limit is `5 × workers` per minute.

---

## 12. Monitoring & Alerting

### Built-in metrics

The dashboard samples every bot every 5 seconds and stores up to 180 samples
(15 minutes of history). For each sample:
- CPU % (via `psutil.Process.cpu_percent`)
- Memory MB (via `psutil.Process.memory_info().rss`)

System-wide metrics (CPU, load, memory, swap, disk, process count) are
captured on each `/api/status` request.

### Health probes

| Endpoint | Use | Behavior |
|---|---|---|
| `/healthz` | Kubernetes liveness, Render health check | Always returns 200 if the process is alive |
| `/readyz` | Kubernetes readiness | 200 if supervisor is attached and config loaded; 503 otherwise |

The Dockerfile wires `/healthz` into `HEALTHCHECK` with a 30s interval,
5s timeout, 15s start period, and 3 retries.

### Webhook alerts

When a bot crashes, MultiBots POSTs to `MB_WEBHOOK_URL`:

```json
{
    "text": "⚠️ MultiBots: bot *my_bot* crashed — exited code=1",
    "content": "⚠️ MultiBots: bot **my_bot** crashed — exited code=1",
    "username": "MultiBots",
    "bot_name": "my_bot",
    "reason": "exited code=1",
    "ts": "2026-07-05T18:40:09Z"
}
```

The payload includes both `text` (Slack format) and `content` (Discord
format) keys for max compatibility. Failed webhook delivery is logged but
never blocks the supervisor.

### External monitoring

Point your external monitor (UptimeRobot, Pingdom, etc.) at:
```
http://your-host:10000/healthz
```

For richer monitoring, scrape `/api/status` with Prometheus (a custom
exporter is on the roadmap — see [#Roadmap](#roadmap)).

---

## 13. Troubleshooting

### Bot won't start

1. **Check the dashboard**: the bot card shows the last error in red.
2. **Check the supervisor log**: `docker logs multibots 2>&1 | grep "my_bot"`.
3. **Verify the run file exists**: The supervisor logs `Bot 'X' run file
   missing: /app/X/main.py` if the file isn't there. This usually means
   `run.sh` failed to clone the repo — check the Docker build output.
4. **Verify the run file is valid Python**: `docker exec -it multibots
   python3 /app/my_bot/main.py` to run it manually.

### Bot keeps crashing

- The supervisor auto-restarts crashed bots up to `max_restarts` (default 5)
  with exponential backoff (2s, 4s, 8s, ..., capped at 120s).
- After hitting the cap, the bot stays "crashed" and won't restart
  automatically. Use the dashboard's **Start** button to retry.
- Check `/api/bots/<name>/logs` for the bot's stdout/stderr.

### Dashboard shows 502 / connection refused

- The dashboard runs on port 10000 by default. Verify with `curl
  http://localhost:10000/healthz` from inside the container.
- If using gunicorn (default Dockerfile CMD), check `docker logs` for
  gunicorn startup errors.

### Forgot the dashboard password

If you used auto-generation, the password is in the first boot logs:
```bash
docker logs multibots 2>&1 | grep "Generated:"
```

If that's gone, set a new one:
```bash
# Generate a new hash:
python -c "import dashboard; print(dashboard.hash_password('new-pw'))"

# Set via env var and restart:
export MB_DASHBOARD_PASSWORD_HASH='pbkdf2_sha256$240000$...'
docker restart multibots
```

### Login locked out

After 5 failed attempts in 1 minute, you'll get HTTP 429. Wait 60 seconds
or restart the container to clear the in-memory limiter.

### Orphan processes after shutdown

If you see bot PIDs still running after `docker stop`, the bot ignored
SIGTERM. Increase `timeout_graceful` (default 10s) for that bot in
`config.json` so the supervisor sends SIGKILL later. For truly stuck
processes, `docker kill multibots` will clean up everything.

### Private repo clone fails in Docker build

1. Verify the token in the URL isn't expired.
2. Check that the URL format is exactly:
   `https://USERNAME:TOKEN@github.com/USERNAME/REPO.git`
3. The build suppresses the URL echo to avoid leaking tokens in logs.
   Test the clone manually:
   ```bash
   git clone 'https://USERNAME:TOKEN@github.com/USERNAME/REPO.git' /tmp/test
   ```

### `run.sh` says "no requirements.txt"

That's a warning, not an error. If your bot has no Python dependencies
beyond the standard library, it's fine. If it does have deps, add a
`requirements.txt` to your bot's repo root.

---

## 14. Testing

MultiBots ships with **117 automated tests** covering every feature.

### Test layout

```
tests/
├── conftest.py              # shared fixtures (fake bots, settings, wait_for)
├── test_config.py           # config schema validation (35 tests)
├── test_supervisor.py       # start/stop/restart/watchdog/shutdown (19 tests)
├── test_metrics.py          # CPU/RAM sampling, history cap, snapshots (5 tests)
├── test_webhook.py          # Slack/Discord webhook delivery (6 tests)
├── test_dashboard_auth.py   # PBKDF2, sessions, rate limit, CSRF (17 tests)
├── test_dashboard_api.py    # all /api/* routes (29 tests)
└── test_integration.py      # end-to-end deployment scenarios (6 tests)
```

### Running the tests

```bash
# From the repo root:
pip install -r requirements.txt pytest
pytest tests/ -v

# With coverage:
pytest tests/ --cov=main --cov=dashboard --cov-report=term-missing

# Just the integration tests:
pytest tests/test_integration.py -v

# Just the auth tests:
pytest tests/test_dashboard_auth.py -v
```

### Live smoke test

The `scripts/smoke_live.py` script boots a real dashboard subprocess on
port 10099 and exercises every endpoint with real HTTP requests. Use this
to verify the system works end-to-end outside of pytest:

```bash
python scripts/smoke_live.py
# → ✅ ALL LIVE SMOKE TESTS PASSED (17 checks)
```

### Backward-compat test

```bash
python scripts/smoke_backward_compat.py
# → ✅ ALL BACKWARD COMPAT TESTS PASSED
```

### What the tests cover

| Category | What's tested |
|---|---|
| **Config** | All field types, validation rules, error paths, backward compat with v1 schema, global inheritance, env coercion, name validation |
| **Supervisor** | Start/stop/restart/enable/disable, watchdog auto-restart, max-restart cap, graceful shutdown (SIGTERM), SIGKILL fallback for stuck bots, concurrent operations (lock safety) |
| **Metrics** | Per-bot CPU/RAM sampling, history cap enforcement, dead bot → zero metrics, system snapshot never raises |
| **Webhook** | Disabled webhooks, successful delivery, HTTP errors, network errors, timeout passthrough |
| **Auth** | PBKDF2 hash format, correct/wrong/corrupted passwords, salt uniqueness, session issue/verify/expiry/tamper, rate limit (5/min, IP-scoped, window expiry), auto-generated password persistence |
| **API** | All read endpoints (status, bots, single bot, logs, metrics history), all action endpoints (start/stop/restart/enable/disable), auth gating on every protected route, CSRF enforcement, 404/400/403 error paths |
| **Integration** | Full deployment from real config.json, dashboard wired to supervisor, login → dashboard → API → action → logout flow, env masking (no secret leak), backward compat with v1 README example, hot-reload scenario, crash → webhook delivery |

---

## 15. Migration Guide (v1 → v2)

### Your existing `config.json` works as-is

The v1 schema (`{bot: {source, env, run}}`) is fully supported. You do not
need to change anything to upgrade.

### What changes when you upgrade

- The dashboard now requires a password (auto-generated on first boot,
  printed to logs). Find it with: `docker logs multibots 2>&1 | grep Generated:`
- Bots now auto-restart on crash (up to 5 times by default).
- The keep-alive pinger is fixed (was pinging `0.0.0.0` which doesn't work
  on all platforms; now pings `127.0.0.1`).
- Bots receive SIGTERM on container stop instead of being orphaned.
- The Docker image runs as non-root (uid 1000).
- Docker HEALTHCHECK is wired to `/healthz`.

### Optional v2 features you can adopt incrementally

```json
{
    "_global": {
        "max_restarts": 10
    },
    "my_legacy_bot": {
        "source": "https://github.com/x/y.git",
        "env": {"TOKEN": "..."},
        "run": "main.py"
    },
    "my_modern_bot": {
        "source": "https://github.com/x/z.git",
        "env": {"TOKEN": "..."},
        "run": "main.py",
        "enabled": true,
        "max_restarts": 20,
        "restart_delay_base": 5.0,
        "args": ["--worker-count", "4"]
    }
}
```

- Add `_global` to set defaults for all bots.
- Add `_dashboard.password_hash` to set a fixed dashboard password.
- Add per-bot `enabled: false` to disable a bot without removing it.
- Add per-bot `max_restarts: 0` to disable auto-restart for that bot.
- Add per-bot `args` to pass command-line arguments.

### What was removed

Nothing. v2 is a strict superset of v1.

---

## 16. Contributing

### Development setup

```bash
git clone https://github.com/maruf009sultan/MultiBots.git
cd MultiBots
pip install -r requirements.txt pytest
pytest tests/ -v
```

### Code style

- Single-file modules (`main.py`, `dashboard.py`) — keep sections clearly
  delimited with header comments.
- Every public class/function has a docstring.
- Defensive error handling: supervisor must never crash on a single bot
  failure.
- Tests are mandatory for new features.

### Pull request checklist

- [ ] Tests pass: `pytest tests/ -v`
- [ ] Live smoke test passes: `python scripts/smoke_live.py`
- [ ] Backward compat test passes: `python scripts/smoke_backward_compat.py`
- [ ] No new dependencies without justification
- [ ] README updated if behavior changed
- [ ] No secrets in code or commit history

### Roadmap

- [ ] Prometheus metrics exporter (`/metrics` endpoint)
- [ ] WebSocket live log streaming (instead of polling)
- [ ] Per-bot log file rotation (instead of in-memory capture)
- [ ] Multi-user auth (OAuth/OIDC)
- [ ] Bot deployment without rebuild (git pull on restart)
- [ ] Config hot-reload without restart
- [ ] Per-bot CPU/RAM limits via cgroups

---

## 17. License

MIT — see `LICENSE` file.

---

## Appendix: Quick Reference

### Common commands

```bash
# Build & run:
docker build -t multibots . && docker run -p 10000:10000 multibots

# View auto-generated password:
docker logs multibots 2>&1 | grep "Generated:"

# Tail supervisor log:
docker logs -f multibots

# Tail a specific bot's log:
docker exec multibots cat /app/logs/multibots.log | grep "bot.my_bot"

# Generate a dashboard password hash:
docker run --rm multibots python -c "import dashboard; print(dashboard.hash_password('pw'))"

# Run tests:
pytest tests/ -v

# Live smoke test:
python scripts/smoke_live.py
```

### Default ports / paths

| What | Default |
|---|---|
| Dashboard HTTP port | 10000 |
| Bot working directory | `/app/<bot_name>` |
| Config file | `/app/config.json` |
| Log directory | `/app/logs` (or `logs/` if running locally) |
| Auto-gen password file | `.multibots_dashboard_pw` (next to config.json) |

### Support

- **Bugs**: [GitHub Issues](https://github.com/maruf009sultan/MultiBots/issues)
- **README source of truth**: this file
- **Code is self-documenting**: read `main.py` top-to-bottom — every section
  has a header comment explaining its role.
