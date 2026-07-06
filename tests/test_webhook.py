"""Unit tests for WebhookNotifier."""
from __future__ import annotations

import pytest
import requests

from main import WebhookNotifier


class TestWebhookEnabled:
    def test_empty_url_means_disabled(self):
        n = WebhookNotifier("")
        assert n.enabled is False

    def test_non_empty_url_means_enabled(self):
        n = WebhookNotifier("https://hooks.slack.com/x")
        assert n.enabled is True


class TestWebhookDelivery:
    def test_disabled_webhook_returns_false(self):
        n = WebhookNotifier("")
        assert n.notify_crash("b1", "test") is False

    def test_successful_delivery(self, monkeypatch):
        n = WebhookNotifier("https://example.com/hook")

        class FakeResp:
            status_code = 200
            text = "ok"

        called = {}
        def fake_post(url, json, timeout, headers):
            called["url"] = url
            called["json"] = json
            called["timeout"] = timeout
            called["headers"] = headers
            return FakeResp()

        monkeypatch.setattr(requests, "post", fake_post)
        assert n.notify_crash("b1", "exited code=1") is True
        assert called["url"] == "https://example.com/hook"
        assert "b1" in called["json"]["text"]
        assert "exited code=1" in called["json"]["text"]
        assert called["json"]["bot_name"] == "b1"
        assert "ts" in called["json"]
        assert "MultiBots" in called["headers"]["User-Agent"]

    def test_http_error_returns_false(self, monkeypatch):
        n = WebhookNotifier("https://example.com/hook")

        class FakeResp:
            status_code = 500
            text = "server error"

        monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp())
        assert n.notify_crash("b1", "boom") is False

    def test_network_error_returns_false(self, monkeypatch):
        n = WebhookNotifier("https://example.com/hook")

        def fake_post(*a, **k):
            raise requests.ConnectionError("network down")

        monkeypatch.setattr(requests, "post", fake_post)
        assert n.notify_crash("b1", "boom") is False

    def test_timeout_passed_through(self, monkeypatch):
        n = WebhookNotifier("https://example.com/hook", timeout=7.5)

        class FakeResp:
            status_code = 200
            text = "ok"

        seen = {}
        def fake_post(url, json, timeout, headers):
            seen["timeout"] = timeout
            return FakeResp()

        monkeypatch.setattr(requests, "post", fake_post)
        n.notify_crash("b1", "boom")
        assert seen["timeout"] == 7.5
