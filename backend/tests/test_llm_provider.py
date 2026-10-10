"""LLM call failure handling. A failed Groq call must (a) retry momentary
network/TLS errors, (b) never retry errors that repeating can't fix, and
(c) tell the user what actually failed — the old message told everyone to
"configure GROQ_API_KEY" even when the key was set and the network was the
problem."""
import ssl

import httpx
import pytest

from app.services import llm_provider
from app.services.llm_provider import DevModeProvider, _SafeProvider

SOURCES = [{"content": "x"}, {"content": "y"}]


class _FlakyInner:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def generate(self, context_text, question):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _tls_error():
    err = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain")
    err.__cause__ = ssl.SSLCertVerificationError("self-signed certificate in certificate chain")
    return err


def _status_error(code):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return httpx.HTTPStatusError("error", request=request, response=httpx.Response(code, request=request))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm_provider.time, "sleep", lambda s: None)


def test_momentary_tls_failure_is_retried_and_the_real_answer_is_returned():
    inner = _FlakyInner([_tls_error(), "Real answer [SOURCE_1]"])
    assert _SafeProvider(inner, SOURCES).generate("ctx", "q") == "Real answer [SOURCE_1]"
    assert inner.calls == 2


def test_persistent_tls_failure_explains_the_certificate_problem_not_a_missing_key():
    inner = _FlakyInner([_tls_error(), _tls_error(), _tls_error()])
    answer = _SafeProvider(inner, SOURCES).generate("ctx", "q")

    assert inner.calls == 3
    assert "certificate verification" in answer
    assert "Configure GROQ_API_KEY" not in answer
    assert answer.startswith("[AI ANSWER UNAVAILABLE]")
    assert "2 authorized source(s)" in answer


def test_bad_api_key_is_not_retried_and_points_at_the_key():
    inner = _FlakyInner([_status_error(401)])
    answer = _SafeProvider(inner, SOURCES).generate("ctx", "q")
    assert inner.calls == 1
    assert "API key" in answer


def test_rate_limit_is_not_retried_and_says_so():
    inner = _FlakyInner([_status_error(429)])
    answer = _SafeProvider(inner, SOURCES).generate("ctx", "q")
    assert inner.calls == 1
    assert "rate-limiting" in answer


def test_unconfigured_llm_still_tells_the_user_to_configure_a_key():
    answer = DevModeProvider(SOURCES).generate("ctx", "q")
    assert answer.startswith("[DEV MODE]")
    assert "Configure GROQ_API_KEY" in answer


def test_no_sources_never_pretends_to_have_an_answer():
    assert "couldn't find enough authorized information" in DevModeProvider([]).generate("ctx", "q")
