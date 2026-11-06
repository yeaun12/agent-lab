"""3.7 /ask SSE 테스트. 진짜 모델과 저장소 대신 가짜를 끼워 넣는다 (dependency_overrides)."""

import asyncio
import json

from httpx import ASGITransport, AsyncClient

from agent_lab.api import app, get_llm_factory, get_toolbox
from agent_lab.core.llm import FakeLLM, ToolCall


class StubToolbox:
    def __init__(self):
        self.specs = []

    def run(self, name, arguments):
        return "httpx/_config.py:246: DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)", True


def fake_factory():
    return FakeLLM([
        FakeLLM.reply(tool_calls=[ToolCall(id="c1", name="grep", arguments='{"pattern": "DEFAULT_TIMEOUT"}')]),
        FakeLLM.reply("기본 타임아웃은 5초다 (httpx/_config.py:246)."),
    ])


def make_client():
    app.dependency_overrides[get_toolbox] = StubToolbox
    app.dependency_overrides[get_llm_factory] = lambda: fake_factory
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def parse_sse(text: str) -> list:
    blocks = [b.removeprefix("data: ") for b in text.split("\n\n") if b]
    return [b if b == "[DONE]" else json.loads(b) for b in blocks]


async def test_ask_streams_step_then_answer():
    async with make_client() as client:
        r = await client.post("/ask", json={"question": "기본 타임아웃?"})
    events = parse_sse(r.text)
    assert r.headers["content-type"].startswith("text/event-stream")
    assert [e if e == "[DONE]" else e["type"] for e in events] == ["step", "answer", "[DONE]"]
    assert "5초" in events[1]["text"]


async def test_concurrent_requests_do_not_mix():
    async with make_client() as client:
        rs = await asyncio.gather(*[client.post("/ask", json={"question": f"질문 {i}"}) for i in range(3)])
    # 요청마다 FakeLLM과 messages가 따로라 셋 다 같은 순서로 끝까지 간다
    assert all([e if e == "[DONE]" else e["type"] for e in parse_sse(r.text)] == ["step", "answer", "[DONE]"] for r in rs)


async def test_model_is_restricted():
    async with make_client() as client:
        r = await client.post("/ask", json={"question": "q", "model": "gpt-9"})
    assert r.status_code == 422