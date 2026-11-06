"""3.6 ReAct 루프 테스트. FakeLLM이 정해 둔 순서대로 답해서 네트워크·한도를 쓰지 않는다."""

from agent_lab.agents.repo_pilot.agent import ask, estimate_tokens, shrink
from agent_lab.core.llm import BadRequest, FakeLLM, RateLimited, ToolCall


class StubToolbox:
    """진짜 저장소 대신 정해진 글을 돌려주는 도구 상자."""

    def __init__(self):
        self.specs = [{"type": "function", "function": {"name": "grep"}}]  # 내용은 FakeLLM이 보지 않는다

    def run(self, name, arguments):
        return f"{name} 결과: httpx/_config.py:246", True


def grep_call(i=1):
    return ToolCall(id=f"c{i}", name="grep", arguments='{"pattern": "DEFAULT_TIMEOUT"}')


async def test_tool_then_answer():
    llm = FakeLLM([FakeLLM.reply(tool_calls=[grep_call()]), FakeLLM.reply("5초다 (httpx/_config.py:246)")])
    result = await ask(llm, "기본 타임아웃?", StubToolbox())
    assert result["stopped"] == "done" and result["steps"] == 1
    assert result["step_log"][0]["tool"] == "grep"
    # 두 번째 호출에는 도구 결과가 tool 메시지로 들어가 있어야 한다
    second = llm.calls[1]["messages"]
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "c1"


async def test_max_steps_gives_partial_answer():
    replies = [FakeLLM.reply(tool_calls=[grep_call(i)]) for i in range(3)] + [FakeLLM.reply("확인한 것까지만")]
    llm = FakeLLM(replies)
    result = await ask(llm, "끝없는 질문", StubToolbox(), max_steps=3)
    assert result["stopped"] == "max_steps" and result["text"] == "확인한 것까지만"
    assert llm.calls[-1]["tools"] is None  # 마지막 호출은 도구 없이


class FlakyLLM(FakeLLM):
    """첫 호출은 Groq처럼 도구 형식 오류(400)를 내고, 그다음부터는 정해 둔 답을 준다."""

    async def chat(self, messages, tools=None, model="smart", **options):
        if not self.calls:
            self.calls.append({"messages": list(messages)})
            raise BadRequest("400: Tool call validation failed: /k: maximum: got 10, want 8")
        return await super().chat(messages, tools, model, **options)


async def test_tool_format_error_is_retried():
    llm = FlakyLLM([FakeLLM.reply("다시 해서 답함")])
    result = await ask(llm, "질문", StubToolbox())
    assert result["text"] == "다시 해서 답함"
    # 두 번째 호출에는 무엇이 틀렸는지 알려 주는 메시지가 붙어 있다
    assert "스키마" in llm.calls[1]["messages"][-1]["content"]


class DailyLimitLLM(FakeLLM):
    """fast로 부르면 하루 한도 429, long으로 부르면 정상."""

    async def chat(self, messages, tools=None, model="smart", **options):
        if model == "fast":
            raise RateLimited(None, "Rate limit reached ... tokens per day (TPD): Limit 200000, Used 200000")
        return await super().chat(messages, tools, model, **options)


async def test_daily_limit_switches_to_long():
    llm = DailyLimitLLM([FakeLLM.reply("Gemini가 답함")])
    result = await ask(llm, "질문", StubToolbox(), model="fast")
    assert result["text"] == "Gemini가 답함" and result["model"] == "long"


def test_shrink_keeps_last_tool_result():
    msgs = [{"role": "tool", "content": "첫 줄\n" + "x" * 5000}, {"role": "tool", "content": "마지막\n" + "y" * 10}]
    before = estimate_tokens(msgs)
    assert shrink(msgs) is True
    assert msgs[0]["content"] == "(줄임) 첫 줄" and msgs[1]["content"].startswith("마지막")
    assert estimate_tokens(msgs) < before
    assert shrink(msgs) is False  # 남은 건 마지막 결과뿐