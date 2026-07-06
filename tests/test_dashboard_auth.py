"""Unit tests for dashboard auth (password hashing, sessions, rate limit, CSRF)."""
from __future__ import annotations

import time

import pytest

import dashboard
from dashboard import (
    DashboardApp, LoginRateLimiter, SessionSigner,
    hash_password, verify_password,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
class TestPasswordHashing:
    def test_hash_format(self):
        h = hash_password("hello")
        assert h.startswith("pbkdf2_sha256$")
        parts = h.split("$")
        assert len(parts) == 4
        assert parts[1] == str(dashboard.PBKDF2_ITERATIONS)

    def test_verify_correct_password(self):
        h = hash_password("s3cret-pass")
        assert verify_password("s3cret-pass", h) is True

    def test_verify_wrong_password(self):
        h = hash_password("s3cret-pass")
        assert verify_password("wrong", h) is False

    def test_verify_corrupted_hash(self):
        assert verify_password("x", "not-a-valid-hash") is False
        assert verify_password("x", "pbkdf2_sha256$abc$notb64$alsobad") is False
        assert verify_password("x", "") is False

    def test_two_hashes_have_different_salts(self):
        h1 = hash_password("same-pass")
        h2 = hash_password("same-pass")
        assert h1 != h2  # different salts
        # But both verify against the same password.
        assert verify_password("same-pass", h1)
        assert verify_password("same-pass", h2)

    def test_constant_time_compare_on_verify(self):
        # Hard to test timing directly, but at least verify both branches
        # return without raising on adversarial input.
        h = hash_password("hello")
        for guess in ["", "x" * 1000, "你好", "null\x00byte"]:
            assert verify_password(guess, h) is False


# ---------------------------------------------------------------------------
# Session signer
# ---------------------------------------------------------------------------
class TestSessionSigner:
    def test_issue_and_verify_roundtrip(self):
        s = SessionSigner(b"secret-key")
        tok = s.issue(role="admin", ttl=60)
        assert s.verify(tok) is True

    def test_verify_with_wrong_secret(self):
        s1 = SessionSigner(b"secret-key-1")
        s2 = SessionSigner(b"secret-key-2")
        tok = s1.issue()
        assert s2.verify(tok) is False

    def test_verify_expired_token(self):
        s = SessionSigner(b"secret-key")
        # Issue then immediately expire by manipulating payload.
        # Simpler: set ttl to 1s, wait 1.1s.
        tok = s.issue(ttl=1)
        time.sleep(1.2)
        assert s.verify(tok) is False

    def test_verify_tampered_token(self):
        s = SessionSigner(b"secret-key")
        tok = s.issue()
        # Flip a character in the signature.
        bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
        assert s.verify(bad) is False

    def test_verify_garbage_returns_false(self):
        s = SessionSigner(b"secret-key")
        assert s.verify("") is False
        assert s.verify("garbage") is False
        assert s.verify("a.b.c") is False


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
class TestRateLimiter:
    def test_allows_up_to_limit(self):
        rl = LoginRateLimiter()
        for _ in range(dashboard.LOGIN_RATE_LIMIT):
            assert rl.allow("1.2.3.4") is True

    def test_blocks_after_limit(self):
        rl = LoginRateLimiter()
        for _ in range(dashboard.LOGIN_RATE_LIMIT):
            rl.allow("1.2.3.4")
        assert rl.allow("1.2.3.4") is False

    def test_separate_ips_independent(self):
        rl = LoginRateLimiter()
        for _ in range(dashboard.LOGIN_RATE_LIMIT):
            rl.allow("1.1.1.1")
        # Different IP still allowed.
        assert rl.allow("2.2.2.2") is True

    def test_window_expires(self):
        rl = LoginRateLimiter()
        # Patch the window to 0.1s for fast testing.
        original = dashboard.LOGIN_RATE_WINDOW
        dashboard.LOGIN_RATE_WINDOW = 0.1
        try:
            for _ in range(dashboard.LOGIN_RATE_LIMIT):
                rl.allow("9.9.9.9")
            assert rl.allow("9.9.9.9") is False
            time.sleep(0.15)
            assert rl.allow("9.9.9.9") is True
        finally:
            dashboard.LOGIN_RATE_WINDOW = original


# ---------------------------------------------------------------------------
# DashboardApp password resolution
# ---------------------------------------------------------------------------
class TestDashboardAppPassword:
    def test_uses_provided_hash(self, settings):
        h = hash_password("my-test-pw")
        settings["dashboard_password_hash"] = h
        app = DashboardApp(settings=settings)
        assert app._password_hash == h
        assert verify_password("my-test-pw", app._password_hash)

    def test_auto_generates_when_missing(self, settings, tmp_path, monkeypatch):
        # Point config_path at tmp_path so the generated file goes there.
        settings["dashboard_password_hash"] = ""
        settings["config_path"] = str(tmp_path / "config.json")
        # Capture the printed password.
        import logging, io
        buf = io.StringIO()
        h = logging.StreamHandler(buf)
        h.setLevel(logging.WARNING)
        logging.getLogger("multibots.dashboard").addHandler(h)
        app = DashboardApp(settings=settings)
        logging.getLogger("multibots.dashboard").removeHandler(h)
        # Either we persisted a file, or kept it in memory.
        assert app._password_hash.startswith("pbkdf2_sha256$")
