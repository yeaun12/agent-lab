"""1.6 검증 실패를 세는 도구 호출 순환. 1.5의 tool_demo.py를 이 내용으로 바꾼다."""

import asyncio
from collections import Counter

from agent_lab.core.llm import LLMClient
from agent_lab.core.tools import TOOLS, run_tool

MAX_FAILS = 2  # 같은 도구의 인자 검증이 이만큼 실패하면 더 묻지 않고 멈춘다


async def ask(
    client: LLMClient, question: str, model: str = "fast", max_rounds: int = 5
) -> dict:
    """질문을 처리하고 {답, 상태, 재시도 횟수}를 돌려준다. 상태: ok / retried / failed"""
    messages = [{"role": "user", "content": question}]
    fails = Counter()  # 도구 이름별 검증 실패 횟수
    for _ in range(max_rounds):
        result = await client.chat(messages, tools=TOOLS, model=model)
        if not result.tool_calls:
            # 실패가 한 번이라도 있었으면 '재시도 후 성공'
            status = "retried" if sum(fails.values()) else "ok"
            return {
                "answer": result.text or "",
                "status": status,
                "retries": sum(fails.values()),
            }
        messages.append(
            {
                "role": "assistant",
                "content": result.text,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": c.arguments},
                    }
                    for c in result.tool_calls
                ],
            }
        )
        for call in result.tool_calls:
            output, ok = run_tool(call.name, call.arguments)
            print(f"  {call.name}({call.arguments}) → {output[:80]}")
            if not ok:
                fails[call.name] += 1
                # 같은 실수를 반복하면 끝낸다 (무한 반복 방지)
                if fails[call.name] > MAX_FAILS:
                    return {
                        "answer": "",
                        "status": "failed",
                        "retries": sum(fails.values()),
                    }
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": output}
            )
    return {"answer": "", "status": "failed", "retries": sum(fails.values())}


async def success_rate(model: str = "local", runs: int = 20):
    """같은 질문을 runs번 돌려 ok / retried / failed 횟수를 센다 (단계 6)."""
    counts = Counter()
    async with LLMClient() as client:
        for i in range(runs):
            outcome = await ask(
                client, "부산 기온을 화씨로 바꾸면 몇 도야?", model=model
            )
            counts[outcome["status"]] += 1
            print(f"{i + 1:2d}/{runs} {outcome['status']}")
    print(dict(counts))


if __name__ == "__main__":
    asyncio.run(success_rate(model="local", runs=20))