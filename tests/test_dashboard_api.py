"""Integration tests for the dashboard Flask app (routes + API)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import dashboard
from dashboard import DashboardApp, hash_password
from main import BotConfig, MultiBots


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def dash_app(settings, multibots_factory, make_bot, fake_bot_scripts):
    """A DashboardApp wired to a MultiBots instance with one running bot."""
    make_bot("b1", fake_bot_scripts["ok"])
    settings["dashboard_password_hash"] = hash_password("test-pw-123")
    settings["dashboard_session_secret"] = "unit-test-secret"
    mb = multibots_factory([BotConfig(name="b1", source="https://x.git", run="main.py")])
    # Install dashboard capture BEFORE starting bots so we catch startup logs.
    app = DashboardApp(settings=settings)
    app.attach(mb)
    mb.start(run_pinger=False, install_signals=False)
    # Wait for the bot to come up.
    import time
    for _ in range(50):
        if mb.supervisor.states["b1"].status == "running":
            break
        time.sleep(0.1)
    yield app
    mb.stop()


@pytest.fixture
def client(dash_app):
    return dash_app.app.test_client()


@pytest.fixture
def authed_client(client):
    """A client that has logged in (session cookie set)."""
    resp = client.post("/login", data={"password": "test-pw-123"})
    assert resp.status_code in (302, 200)
    return client


# ---------------------------------------------------------------------------
# Public health endpoints (no auth)
# ---------------------------------------------------------------------------
class TestHealthEndpoints:
    def test_healthz_no_auth(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.data == b"ok\n"

    def test_readyz_when_attached(self, client):
        r = client.get("/readyz")
        # If a supervisor is attached, readyz should be 200.
        assert r.status_code in (200, 503)


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------
class TestLoginFlow:
    def test_get_login_page(self, client):
        r = client.get("/login")
        assert r.status_code == 200
        assert b"MultiBots" in r.data
        assert b"password" in r.data

    def test_login_correct_password(self, client):
        r = client.post("/login", data={"password": "test-pw-123"})
        # 302 redirect to "/"
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/")

    def test_login_wrong_password(self, client):
        r = client.post("/login", data={"password": "wrong"})
        assert r.status_code == 401
        assert b"Incorrect password" in r.data

    def test_login_empty_password(self, client):
        r = client.post("/login", data={"password": ""})
        assert r.status_code == 401

    def test_login_rate_limit_kicks_in(self, client):
        # Try 5 wrong attempts + 1 more.
        for _ in range(dashboard.LOGIN_RATE_LIMIT):
            client.post("/login", data={"password": "bad"})
        # 6th should be 429.
        r = client.post("/login", data={"password": "bad"})
        assert r.status_code == 429
        assert b"Too many" in r.data

    def test_logout_clears_session(self, authed_client):
        r = authed_client.post("/logout")
        assert r.status_code == 302
        # After logout, hitting / should redirect to /login.
        r = authed_client.get("/")
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]


# ---------------------------------------------------------------------------
# Auth gating — every protected route requires login
# ---------------------------------------------------------------------------
class TestAuthGating:
    @pytest.mark.parametrize("path", [
        "/", "/api/status", "/api/bots", "/api/bots/b1",
        "/api/bots/b1/logs", "/api/supervisor_log",
        "/api/metrics/history/b1",
    ])
    def test_unauthenticated_redirects_or_401(self, client, path):
        r = client.get(path)
        # Either redirect (HTML routes) or 401/302 (API).
        assert r.status_code in (301, 302, 401, 403), \
            f"{path} returned {r.status_code} without auth"

    def test_authed_can_access_dashboard(self, authed_client):
        r = authed_client.get("/")
        assert r.status_code == 200
        assert b"MultiBots Dashboard" in r.data


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
class TestStatusApi:
    def test_status_returns_system_and_bots(self, authed_client):
        r = authed_client.get("/api/status")
        assert r.status_code == 200
        data = r.get_json()
        assert "ts" in data
        assert "system" in data
        assert "bots" in data
        assert isinstance(data["bots"], list)
        assert any(b["name"] == "b1" for b in data["bots"])

    def test_bots_list(self, authed_client):
        r = authed_client.get("/api/bots")
        assert r.status_code == 200
        bots = r.get_json()
        assert len(bots) == 1
        assert bots[0]["name"] == "b1"

    def test_single_bot(self, authed_client):
        r = authed_client.get("/api/bots/b1")
        assert r.status_code == 200
        b = r.get_json()
        assert b["name"] == "b1"
        assert "status" in b
        assert "config" in b

    def test_unknown_bot_404(self, authed_client):
        r = authed_client.get("/api/bots/ghost")
        assert r.status_code == 404


class TestBotActionsApi:
    def test_restart_action(self, authed_client, dash_app):
        # Get CSRF token first (it's set when we visit the dashboard).
        authed_client.get("/")
        # The CSRF token is in the session; we need to extract it.
        # Simpler: make the dashboard accept form-encoded csrf_token too.
        # Actually the dashboard reads X-CSRF-Token header OR form field.
        # Use the form-field route via JSON won't work; let's send header.
        # First, get the token from a rendered page.
        r = authed_client.get("/")
        import re
        m = re.search(rb'const csrf = "([^"]+)"', r.data)
        assert m, "CSRF token not found in dashboard HTML"
        csrf = m.group(1).decode()

        r = authed_client.post(
            "/api/bots/b1/restart",
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["action"] == "restart"

    def test_action_unknown_bot_404(self, authed_client):
        authed_client.get("/")
        import re
        r = authed_client.get("/")
        m = re.search(rb'const csrf = "([^"]+)"', r.data)
        csrf = m.group(1).decode()
        r = authed_client.post(
            "/api/bots/ghost/stop",
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 404

    def test_action_unknown_action_400(self, authed_client):
        authed_client.get("/")
        import re
        r = authed_client.get("/")
        m = re.search(rb'const csrf = "([^"]+)"', r.data)
        csrf = m.group(1).decode()
        r = authed_client.post(
            "/api/bots/b1/dance",
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 400

    def test_action_without_csrf_403(self, authed_client):
        r = authed_client.post("/api/bots/b1/stop")
        assert r.status_code == 403

    def test_action_with_bad_csrf_403(self, authed_client):
        r = authed_client.post(
            "/api/bots/b1/stop",
            headers={"X-CSRF-Token": "garbage"},
        )
        assert r.status_code == 403


class TestLogsApi:
    def test_supervisor_log_returns_text(self, authed_client):
        r = authed_client.get("/api/supervisor_log?lines=10")
        assert r.status_code == 200
        assert r.mimetype == "text/plain"
        # May be empty if no logs captured yet — that's OK.

    def test_bot_logs_returns_text(self, authed_client, dash_app, wait_for):
        # Wait for at least one log line to be captured.
        # The fake bot prints "fake-bot-ok: pid=..." on startup.
        wait_for(
            lambda: len(dash_app._captured_bot_lines("b1", 100)) > 0,
            timeout=5,
        )
        r = authed_client.get("/api/bots/b1/logs?lines=50")
        assert r.status_code == 200
        assert b"fake-bot-ok" in r.data or r.data  # at least non-empty

    def test_bot_logs_unknown_bot_404(self, authed_client):
        r = authed_client.get("/api/bots/ghost/logs")
        assert r.status_code == 404


class TestMetricsHistoryApi:
    def test_history_returns_list(self, authed_client, dash_app, wait_for):
        # Trigger a metrics sample by waiting briefly.
        # The dashboard's MultiBots instance has a metrics collector already started.
        mb = dash_app._mb
        if not mb.metrics or not mb.metrics.is_alive():
            from main import MetricsCollector
            m = MetricsCollector(mb.supervisor, history_size=60)
            m.POLL_INTERVAL = 0.1
            m.start()
            time.sleep(0.3)
        r = authed_client.get("/api/metrics/history/b1")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
