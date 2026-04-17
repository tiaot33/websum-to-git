from __future__ import annotations

from types import SimpleNamespace

import pytest

from websum_to_git.pipeline import HtmlToObsidianPipeline, _RATE_LIMIT_RETRY_WAIT_SECONDS


class FakeRateLimitError(Exception):
    def __init__(self) -> None:
        super().__init__("429 Too Many Requests")
        self.status_code = 429


class FakeServerError(Exception):
    def __init__(self) -> None:
        super().__init__("500 Internal Server Error")
        self.status_code = 500


class FakeLLMClient:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls = 0

    def generate(self, *, system_prompt: str | None, user_content: str) -> str:
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _build_pipeline() -> HtmlToObsidianPipeline:
    pipeline = HtmlToObsidianPipeline.__new__(HtmlToObsidianPipeline)
    pipeline._config = SimpleNamespace()
    pipeline._llm = None
    pipeline._fast_llm = None
    pipeline._publisher = None
    pipeline._telegraph = None
    return pipeline


def test_generate_with_retry_retries_once_after_429(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = _build_pipeline()
    client = FakeLLMClient([FakeRateLimitError(), "ok"])
    sleep_calls: list[int] = []

    monkeypatch.setattr("websum_to_git.pipeline.time.sleep", sleep_calls.append)

    result = pipeline._generate_with_retry(client, system_prompt="sys", user_content="user")

    assert result == "ok"
    assert client.calls == 2
    assert sleep_calls == [_RATE_LIMIT_RETRY_WAIT_SECONDS]


def test_generate_with_retry_does_not_retry_non_429(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = _build_pipeline()
    client = FakeLLMClient([FakeServerError()])
    sleep_calls: list[int] = []

    monkeypatch.setattr("websum_to_git.pipeline.time.sleep", sleep_calls.append)

    with pytest.raises(FakeServerError):
        pipeline._generate_with_retry(client, system_prompt="sys", user_content="user")

    assert client.calls == 1
    assert sleep_calls == []
