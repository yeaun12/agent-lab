"""3.6 질문 하나 해 보기. 실행: uv run python scripts\\ask.py "기본 타임아웃은 몇 초야?" fast"""

import asyncio
import sys

from agent_lab.agents.repo_pilot.agent import ask
from agent_lab.agents.repo_pilot.tools import RepoToolbox
from agent_lab.core.llm import LLMClient


async def main():
    question = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "fast"
    async with LLMClient() as client:
        result = await ask(client, question, RepoToolbox("httpx"), model=model)
    for s in result["step_log"]:
        mark = "O" if s["ok"] else "X"
        print(f"[{s['n']}] {mark} {s['tool']}({s['args']})  {s['tokens']}토큰 {s['ms']}ms")
        print("    →", s["result_preview"].split("\n")[0][:100])
    print(f"\n답 ({result['stopped']}, 모델 {result['model']}, 호출 {result['calls']}회, {result['tokens']}토큰):")
    print(result["text"])


asyncio.run(main())