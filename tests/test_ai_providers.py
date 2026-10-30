"""Tests for ai_providers.py — uses mocks, no real API calls."""
import json
import pytest
from unittest.mock import MagicMock, patch

import ai_providers
from ai_providers import call_provider, ProviderError, ProviderBothResult


def _mock_gemini_response(text: str):
    response = MagicMock()
    response.text = text
    response.candidates = []
    return response


def _mock_gemini_none_response():
    response = MagicMock()
    response.text = None
    candidate = MagicMock()
    candidate.finish_reason = "SAFETY"
    response.candidates = [candidate]
    return response


def _mock_groq_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


GOOD_JSON = json.dumps({"ok": True})


class TestCallGemini:
    def test_returns_parsed_dict(self):
        with patch.object(ai_providers, "gemini_client") as mock_client:
            mock_client.models.generate_content.return_value = _mock_gemini_response(GOOD_JSON)
            result = ai_providers.call_gemini("prompt")
        assert result == {"ok": True}

    def test_raises_on_none_text(self):
        with patch.object(ai_providers, "gemini_client") as mock_client:
            mock_client.models.generate_content.return_value = _mock_gemini_none_response()
            with pytest.raises(ProviderError) as exc_info:
                ai_providers.call_gemini("prompt")
        assert "SAFETY" in str(exc_info.value)
        assert exc_info.value.provider == "gemini"

    def test_raises_when_client_not_configured(self):
        with patch.object(ai_providers, "gemini_client", None):
            with pytest.raises(ProviderError) as exc_info:
                ai_providers.call_gemini("prompt")
        assert exc_info.value.provider == "gemini"

    def test_strips_markdown_fences(self):
        with patch.object(ai_providers, "gemini_client") as mock_client:
            mock_client.models.generate_content.return_value = _mock_gemini_response(
                "```json\n" + GOOD_JSON + "\n```"
            )
            result = ai_providers.call_gemini("prompt")
        assert result == {"ok": True}


class TestCallGroq:
    def test_returns_parsed_dict(self):
        with patch.object(ai_providers, "groq_client") as mock_client:
            mock_client.chat.completions.create.return_value = _mock_groq_response(GOOD_JSON)
            result = ai_providers.call_groq("prompt")
        assert result == {"ok": True}

    def test_raises_on_none_content(self):
        with patch.object(ai_providers, "groq_client") as mock_client:
            msg = MagicMock()
            msg.content = None
            choice = MagicMock()
            choice.message = msg
            completion = MagicMock()
            completion.choices = [choice]
            mock_client.chat.completions.create.return_value = completion
            with pytest.raises(ProviderError) as exc_info:
                ai_providers.call_groq("prompt")
        assert exc_info.value.provider == "groq"

    def test_raises_when_client_not_configured(self):
        with patch.object(ai_providers, "groq_client", None):
            with pytest.raises(ProviderError) as exc_info:
                ai_providers.call_groq("prompt")
        assert exc_info.value.provider == "groq"


class TestCallProvider:
    def test_gemini_mode_returns_dict(self):
        with patch("ai_providers.call_gemini", return_value={"ok": True}):
            result = call_provider("prompt", provider="gemini")
        assert result == {"ok": True}

    def test_gemini_mode_falls_back_to_groq(self):
        with patch("ai_providers.call_gemini", side_effect=ProviderError("fail", "gemini")):
            with patch("ai_providers.call_groq", return_value={"ok": "groq"}):
                result = call_provider("prompt", provider="gemini")
        assert result == {"ok": "groq"}

    def test_groq_mode_no_fallback(self):
        with patch("ai_providers.call_groq", return_value={"ok": True}) as mock_groq:
            with patch("ai_providers.call_gemini") as mock_gemini:
                result = call_provider("prompt", provider="groq")
        mock_groq.assert_called_once()
        mock_gemini.assert_not_called()
        assert result == {"ok": True}

    def test_both_mode_returns_both_results(self):
        with patch("ai_providers.call_gemini", return_value={"src": "gemini"}):
            with patch("ai_providers.call_groq", return_value={"src": "groq"}):
                result = call_provider("prompt", provider="both")
        assert isinstance(result, ProviderBothResult)
        assert result.gemini == {"src": "gemini"}
        assert result.groq == {"src": "groq"}

    def test_both_mode_survives_gemini_failure(self):
        with patch("ai_providers.call_gemini", side_effect=Exception("Gemini down")):
            with patch("ai_providers.call_groq", return_value={"src": "groq"}):
                result = call_provider("prompt", provider="both")
        assert isinstance(result, ProviderBothResult)
        assert result.gemini is None
        assert result.groq == {"src": "groq"}

    def test_both_mode_survives_groq_failure(self):
        with patch("ai_providers.call_gemini", return_value={"src": "gemini"}):
            with patch("ai_providers.call_groq", side_effect=Exception("Groq down")):
                result = call_provider("prompt", provider="both")
        assert isinstance(result, ProviderBothResult)
        assert result.gemini == {"src": "gemini"}
        assert result.groq is None

    def test_default_provider_is_gemini(self):
        with patch("ai_providers.call_gemini", return_value={"ok": True}) as mock_gemini:
            result = call_provider("prompt")
        mock_gemini.assert_called_once_with("prompt")
        assert result == {"ok": True}


class TestCallProviderTracked:
    def test_tracked_returns_primary_engine_on_success(self, monkeypatch):
        monkeypatch.setattr(ai_providers, "call_gemini", lambda p: {"ok": 1})
        result, engine = ai_providers.call_provider_tracked("prompt", "gemini")
        assert result == {"ok": 1}
        assert engine == "gemini"

    def test_tracked_rate_limit_retries_once_then_succeeds(self, monkeypatch):
        calls = {"n": 0}

        def flaky(prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Exception("429 RESOURCE_EXHAUSTED. Please retry in 2.5s.")
            return {"ok": 2}

        slept = {}
        monkeypatch.setattr(ai_providers, "call_gemini", flaky)
        monkeypatch.setattr(ai_providers.time, "sleep", lambda s: slept.setdefault("s", s))
        result, engine = ai_providers.call_provider_tracked("prompt", "gemini")
        assert result == {"ok": 2}
        assert engine == "gemini"
        assert slept["s"] == 2.5

    def test_tracked_falls_back_to_other_engine_after_retry_fails(self, monkeypatch):
        def always_429(prompt):
            raise Exception("Error code: 429 - rate limit reached")

        monkeypatch.setattr(ai_providers, "call_gemini", always_429)
        monkeypatch.setattr(ai_providers, "call_groq", lambda p: {"ok": 3})
        monkeypatch.setattr(ai_providers.time, "sleep", lambda s: None)
        result, engine = ai_providers.call_provider_tracked("prompt", "gemini")
        assert result == {"ok": 3}
        assert engine == "groq"

    def test_tracked_non_rate_limit_falls_back_immediately(self, monkeypatch):
        def boom(prompt):
            raise Exception("Gemini returned None text")

        sleeps = []
        monkeypatch.setattr(ai_providers, "call_gemini", boom)
        monkeypatch.setattr(ai_providers, "call_groq", lambda p: {"ok": 4})
        monkeypatch.setattr(ai_providers.time, "sleep", lambda s: sleeps.append(s))
        result, engine = ai_providers.call_provider_tracked("prompt", "gemini")
        assert engine == "groq"
        assert sleeps == []

    def test_tracked_raises_when_all_engines_fail(self, monkeypatch):
        def boom(prompt):
            raise Exception("dead")

        monkeypatch.setattr(ai_providers, "call_gemini", boom)
        monkeypatch.setattr(ai_providers, "call_groq", boom)
        monkeypatch.setattr(ai_providers, "call_ollama", boom)
        monkeypatch.setattr(ai_providers.time, "sleep", lambda s: None)
        with pytest.raises(Exception):
            ai_providers.call_provider_tracked("prompt", "gemini")

    def test_tracked_falls_back_to_local_ollama_when_cloud_engines_fail(self, monkeypatch):
        """The local engine needs no API key and must still answer.

        Upstream had only Gemini and Groq in the chain, so a machine with no
        cloud keys rejected every job with "client not configured".
        """
        def boom(prompt):
            raise Exception("client not configured")

        monkeypatch.setattr(ai_providers, "call_gemini", boom)
        monkeypatch.setattr(ai_providers, "call_groq", boom)
        monkeypatch.setattr(ai_providers, "call_ollama", lambda p: {"ok": "local"})
        result, engine = ai_providers.call_provider_tracked("prompt", "gemini")
        assert result == {"ok": "local"}
        assert engine == "ollama"

    def test_tracked_groq_primary_falls_back_to_gemini(self, monkeypatch):
        def boom(prompt):
            raise Exception("Error code: 429")

        monkeypatch.setattr(ai_providers, "call_groq", boom)
        monkeypatch.setattr(ai_providers, "call_gemini", lambda p: {"ok": 5})
        monkeypatch.setattr(ai_providers.time, "sleep", lambda s: None)
        result, engine = ai_providers.call_provider_tracked("prompt", "groq")
        assert engine == "gemini"
