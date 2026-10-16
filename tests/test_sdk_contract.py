"""Exercise the real optional SDK against a mock HTTP transport, without API access."""
import json

import pytest

from auto_effort import EffortRouter, TypeSafeBackend


def test_official_sdk_request_and_response_contract(monkeypatch):
    sdk = pytest.importorskip("typesafe_sdk")
    httpx = pytest.importorskip("httpx2")
    real_client = sdk.TypeSafeClient
    seen = []

    def handle(request):
        body = json.loads(request.content)
        seen.append(body)
        assert body["state"]["request"] == "Fix a typo"
        assert body["questions"]["effort"]["type"] == "choice"
        assert "other" in body["questions"]["effort"]["criteria"]
        return httpx.Response(200, json={
            "model": "jev-1.13.0",
            "answers": {"effort": {
                "type": "choice", "choice": "low", "confidence": 0.99,
                "probabilities": {"low": 0.99, "medium": 0.005, "high": 0.004, "other": 0.001},
            }},
            "usage": {"input_tokens": 100, "output_tokens": 10},
        })

    def client(**kwargs):
        assert kwargs["retry"].max_retries == 0
        return real_client(api_key="fake-test-key", transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(sdk, "TypeSafeClient", client)
    decision = EffortRouter(TypeSafeBackend()).pick("Fix a typo")
    assert (decision.effort, decision.source, decision.confidence) == ("low", "jev", 0.99)
    assert len(seen) == 1


def test_official_openrouter_sdk_contract_without_network(monkeypatch):
    sdk = pytest.importorskip("openrouter")
    httpx = pytest.importorskip("httpx")
    from auto_effort import OpenRouterBackend
    real_client = sdk.OpenRouter
    seen = []

    def handle(request):
        body = json.loads(request.content)
        seen.append(body)
        assert body["model"] == "typesafe/jev-1.13"
        assert body["state"]["request"] == "Fix a typo"
        assert body["questions"]["effort"]["type"] == "choice"
        return httpx.Response(200, json={
            "id": "test-decision", "provider": "test-provider", "model": "typesafe/jev-1.13",
            "answers": {"effort": {"type": "choice", "choice": "low", "confidence": 0.99,
                "probabilities": {"low": 0.99, "medium": 0.005, "high": 0.004, "other": 0.001}}},
            "usage": {"input_tokens": 100, "output_tokens": 0, "cost": 0.00002},
        })

    def factory(**kwargs):
        assert kwargs["retry_config"] is None
        return real_client(client=httpx.Client(transport=httpx.MockTransport(handle)), **kwargs)

    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-test-key")
    monkeypatch.setattr(sdk, "OpenRouter", factory)
    decision = EffortRouter(OpenRouterBackend()).pick("Fix a typo")
    assert (decision.effort, decision.source, decision.cost_usd) == ("low", "jev", 0.00002)
    assert len(seen) == 1
