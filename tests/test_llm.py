"""1.4 LLMClient 테스트.

- 표시 없는 테스트: 가짜 서버(MockTransport)로 돈다 → 네트워크·무료 한도 사용 없음
- @pytest.mark.live 테스트: 실제 모델을 부른다 → `uv run pytest -m live`로 따로 실행
"""

import httpx
import pytest

from agent_lab.core.llm import (
    BadRequest,
    FakeLLM,
    LLMClient,
    LLMTimeout,
    ProviderError,
    RateLimited,
)

# 테스트용 별칭 하나 (실제 주소는 쓰이지 않는다)
MODELS = {
    "test": {
        "provider": "fake",
        "base_url": "http://fake/v1",
        "model": "m",
        "api_key_env": None,
    }
}


def client_with(handler):
    """가짜 서버를 끼운 LLMClient. handler가 요청을 받아 원하는 응답을 돌려준다."""
    return LLMClient(models=MODELS, transport=httpx.MockTransport(handler))


async def test_chat_parses_answer():
    def handler(request):
        # 공급자가 돌려주는 모양을 흉내 낸다
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "안녕"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    async with client_with(handler) as client:
        result = await client.chat([{"role": "user", "content": "hi"}], model="test")
    assert result.text == "안녕"
    assert result.usage.completion_tokens == 1


@pytest.mark.parametrize(
    ("status", "error"),  # 상태 코드마다 어떤 내 예외로 바뀌어야 하는지
    [(429, RateLimited), (401, BadRequest), (503, ProviderError), (404, BadRequest)],
)
async def test_errors_are_mapped(status, error):
    def handler(request):
        return httpx.Response(status, headers={"retry-after": "2"}, text="boom")

    async with client_with(handler) as client:
        with pytest.raises(error) as exc_info:  # 이 블록 안에서 error가 나야 통과
            await client.chat([{"role": "user", "content": "hi"}], model="test")
    if error is RateLimited:
        assert exc_info.value.retry_after == 2.0


async def test_timeout_is_mapped():
    def handler(request):
        raise httpx.ReadTimeout("느림", request=request)  # 응답이 안 오는 상황

    async with client_with(handler) as client:
        with pytest.raises(LLMTimeout):
            await client.chat([{"role": "user", "content": "hi"}], model="test")


async def test_fake_llm():
    fake = FakeLLM([FakeLLM.reply("첫 답"), FakeLLM.reply("둘째 답")])
    first = await fake.chat([{"role": "user", "content": "a"}])
    second = await fake.chat([{"role": "user", "content": "b"}])
    assert (first.text, second.text) == ("첫 답", "둘째 답")
    assert len(fake.calls) == 2  # 요청이 두 번 기록됐다


@pytest.mark.live
async def test_local_model_answers():
    # 실제 Ollama를 부른다. Ollama가 켜져 있어야 한다
    async with LLMClient() as client:
        result = await client.chat(
            [{"role": "user", "content": "Say hi in one word."}], model="local"
        )
    assert result.text  # 빈 답이 아니면 통과
    assert result.provider == "ollama"


@pytest.mark.live
async def test_fast_model_answers():
    # 실제 Groq를 부른다. 무료 한도를 1회 쓴다
    async with LLMClient() as client:
        result = await client.chat(
            [{"role": "user", "content": "Say hi in one word."}], model="fast"
        )
    assert result.text
    assert result.provider == "groq"
