"""3.6 프레임워크 없이 만든 ReAct 루프: 생각(모델) → 행동(도구) → 관찰(결과) → 반복.
run_events()는 단계마다 이벤트를 하나씩 내보낸다 → 3.7 SSE가 이것을 그대로 브라우저로 흘린다."""

import asyncio
import json
import time
from collections.abc import AsyncIterator

from pydantic import BaseModel

from agent_lab.agents.repo_pilot.tools import RepoToolbox
from agent_lab.core.llm import BadRequest, RateLimited, RequestTooLarge

SYSTEM = """너는 httpx 저장소의 코드를 읽고 질문에 답하는 도우미다.
규칙:
1. 추측하지 않는다. 반드시 도구로 코드나 문서를 확인한 뒤 답한다.
2. 답의 모든 주장 뒤에 근거를 `경로:줄` 형식으로 붙인다. 예: httpx/_config.py:246
3. 정확한 이름(함수, 상수, 환경 변수)을 알면 grep, 모르면 search_code로 시작하고, 근거는 read_file로 확인한다.
4. 도구로 찾지 못하면 지어내지 말고 '찾지 못함'이라고 답한다.
5. 한국어로 3~6문장 안에 답한다."""

TOKEN_SOFT_LIMIT = 6000  # Groq 무료 등급은 요청 하나가 8K를 넘으면 413 → 여유를 두고 6K에서 줄인다


class Step(BaseModel):
    n: int
    thought: str  # 모델이 도구를 부르며 함께 쓴 글 (없으면 빈 글)
    tool: str
    args: str
    result_preview: str
    ok: bool
    tokens: int  # 이 단계를 정한 모델 호출의 입력+출력 토큰
    ms: int


def estimate_tokens(messages: list[dict]) -> int:
    """대략 3글자 = 1토큰으로 어림한다 (한글·코드가 섞이면 영어보다 토큰이 많다). 정확한 계산은 4.4."""
    return len(json.dumps(messages, ensure_ascii=False)) // 3


def shrink(messages: list[dict]) -> bool:
    """가장 오래된 도구 결과 하나를 첫 줄만 남기고 줄인다. 줄일 게 없으면 False."""
    tool_msgs = [m for m in messages if m["role"] == "tool" and not m["content"].startswith("(줄임)")]
    if len(tool_msgs) <= 1:  # 마지막 결과는 남겨 둔다
        return False
    first_line = tool_msgs[0]["content"].split("\n", 1)[0]
    tool_msgs[0]["content"] = f"(줄임) {first_line[:150]}"
    return True


def tool_call_message(c) -> dict:
    """모델의 도구 호출을 대화 기록용 모양으로. Gemini가 준 extra_content는 꼭 그대로 돌려준다."""
    msg = {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
    if c.extra:
        msg["extra_content"] = c.extra
    return msg


def flatten(messages: list[dict], ending: str = "") -> list[dict]:
    """도구 호출 기록을 빼고 '질문 + 지금까지 확인한 내용' 글 하나로 다시 묶는다. 쓰는 곳 두 군데:
    ① 마무리 답변: 도구 기록이 남아 있으면 '도구 없이 답하라'고 해도 모델이 또 도구를 부르고 Groq가 400으로 거절한다
    ② 공급자 바꾸기(fast → long): Groq가 만든 도구 기록에는 Gemini의 thought_signature가 없어 Gemini가 거절한다
    (둘 다 이 PC에서 겪음)"""
    question = messages[1]["content"]
    seen = "\n\n".join(m["content"][:1500] for m in messages if m["role"] == "tool")
    text = f"질문: {question}" + (f"\n\n지금까지 도구로 확인한 내용:\n{seen}" if seen else "")
    return [messages[0], {"role": "user", "content": text + (f"\n\n{ending}" if ending else "")}]


def is_tool_format_error(e: BadRequest) -> bool:
    """Groq는 모델이 만든 도구 호출을 서버에서 먼저 검사해 400으로 돌려준다 (이 PC에서 겪음).
    예: 'Tool call validation failed ... /k: maximum: got 10, want 8', 'Tool choice is none, but model called a tool'"""
    text = str(e)
    return "Tool call validation failed" in text or "called a tool" in text or "tool_use_failed" in text


async def call_model(client, messages, tools, model) -> tuple:
    """한도와 형식 오류에 바로 실패하지 않게 감싼다. (결과, 실제로 쓴 모델)을 돌려준다.
    - 429 분당 한도: retry_after만큼 기다렸다 다시. 하루 한도: 바로 long으로. 제대로 된 제한기는 4.1에서 만든다.
    - 413: 오래된 도구 결과를 줄이고, 그래도 크면 긴 컨텍스트 모델(long)로 넘긴다.
    - 400 도구 형식 오류: 무엇이 틀렸는지 모델에게 알려 주고 다시 시킨다 (2.6 재시도와 같은 생각)."""
    for _ in range(6):
        while model != "long" and estimate_tokens(messages) > TOKEN_SOFT_LIMIT and shrink(messages):
            pass
        try:
            return await client.chat(messages, tools=tools, model=model), model
        except RateLimited as e:
            # 하루 한도(TPD·RPD)는 기다려도 오늘은 안 풀린다 → 다른 공급자로 넘긴다 (이 PC에서 겪음)
            daily = "per day" in str(e).lower() or "perday" in str(e).lower()  # Groq: 'per day', Gemini: 'PerDay'
            if daily or (e.retry_after or 0) > 60:
                if model == "long":
                    raise
                model = "long"
                messages[:] = flatten(messages)  # [:]: 같은 목록을 고쳐서 run_events 쪽 messages도 바뀌게
                continue
            # 분당 한도는 잠깐 기다리면 풀린다. Gemini는 retry_after를 안 줄 때가 있어 기본 20초
            await asyncio.sleep(min(e.retry_after or 20, 60))
        except RequestTooLarge:
            if not shrink(messages):
                model = "long"
                messages[:] = flatten(messages)
        except BadRequest as e:
            if not is_tool_format_error(e):
                raise  # 키 오류, 모델 이름 오류 등은 다시 해도 안 된다
            hint = "도구는 쓰지 말고 글로만 답한다." if not tools else "도구 인자를 스키마(최솟값·최댓값·필수 항목)에 맞게 다시 호출한다."
            messages.append({"role": "user", "content": f"방금 응답이 거절됐다: {str(e)[:200]} → {hint}"})
    raise RuntimeError("모델 호출이 계속 실패했다 (한도 초과 또는 형식 오류 반복)")


async def run_events(client, question: str, toolbox: RepoToolbox, model: str = "fast", max_steps: int = 8, plan: str | None = None) -> AsyncIterator[dict]:
    """질문 하나를 처리하며 이벤트를 내보낸다. 종류: step, answer"""
    system = SYSTEM + (f"\n\n먼저 세운 계획:\n{plan}" if plan else "")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    total_tokens, calls = 0, 0
    for n in range(1, max_steps + 1):
        start = time.perf_counter()
        result, model = await call_model(client, messages, toolbox.specs, model)
        calls += 1
        used = result.usage.prompt_tokens + result.usage.completion_tokens
        total_tokens += used
        if not result.tool_calls:  # 도구를 더 안 부르면 그게 최종 답
            yield {"type": "answer", "text": result.text or "", "steps": n - 1, "calls": calls, "tokens": total_tokens, "stopped": "done", "model": model}
            return
        messages.append({
            "role": "assistant",
            "content": result.text,
            "tool_calls": [tool_call_message(c) for c in result.tool_calls],
        })
        for call in result.tool_calls:
            output, ok = toolbox.run(call.name, call.arguments)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
            step = Step(n=n, thought=result.text or "", tool=call.name, args=call.arguments, result_preview=output[:200], ok=ok, tokens=used, ms=round((time.perf_counter() - start) * 1000))
            yield {"type": "step", **step.model_dump()}
    # max_steps에 닿았다: 도구 없이 지금까지 모은 정보로 부분 답변을 만든다
    final = flatten(messages, "이 내용만으로 답한다. 확인하지 못한 부분은 '확인 못 함'이라고 쓴다.")
    result, model = await call_model(client, final, None, model)
    calls += 1
    total_tokens += result.usage.prompt_tokens + result.usage.completion_tokens
    yield {"type": "answer", "text": result.text or "", "steps": max_steps, "calls": calls, "tokens": total_tokens, "stopped": "max_steps", "model": model}


async def make_plan(client, question: str, model: str = "fast") -> str:
    """계획-실행 변형의 '계획' 부분: 도구 없이 단계 목록만 먼저 받는다."""
    messages = [
        {"role": "system", "content": "너는 httpx 저장소 질문에 답하기 위한 조사 계획을 세운다. 쓸 수 있는 도구: search_code, read_file, list_dir, grep. 번호 목록으로 3단계 이내, 각 단계 한 줄."},
        {"role": "user", "content": question},
    ]
    result, _ = await call_model(client, messages, None, model)
    return (result.text or "").strip()


async def ask(client, question: str, toolbox: RepoToolbox, model: str = "fast", max_steps: int = 8, mode: str = "react") -> dict:
    """이벤트를 모아 {answer, steps[], ...} 하나로 돌려준다. mode='plan'이면 계획을 먼저 세운다."""
    plan = await make_plan(client, question, model) if mode == "plan" else None
    steps = []
    async for event in run_events(client, question, toolbox, model, max_steps, plan):
        if event["type"] == "step":
            steps.append(event)
        else:
            return {**event, "step_log": steps, "plan": plan}
    raise RuntimeError("answer 이벤트 없이 끝났다")