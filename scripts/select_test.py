"""1.5 모델별 도구 선택률. 실행: uv run python scripts\\select_test.py"""

import asyncio
import sys

from agent_lab.core.llm import LLMClient
from agent_lab.core.tools import TOOLS

# (질문, 기대하는 도구). None = 도구가 필요 없는 질문
SCENARIOS = [
    ("서울 날씨 어때?", "get_weather"),
    ("123 곱하기 45는?", "calculate"),
    ("부산에 지금 비 와?", "get_weather"),
    ("(17 + 3) / 4 계산해 줘", "calculate"),
    ("제주 기온 알려 줘", "get_weather"),
    ("1024 나누기 8은?", "calculate"),
    ("안녕?", None),
    ("파이썬이 뭐야?", None),
    ("고마워!", None),
    ("좋아하는 색이 뭐야?", None),
]


async def selection_rate(model: str):
    correct = 0
    async with LLMClient() as client:
        for question, expected in SCENARIOS:
            # 순환 없이 첫 응답만 본다: '어떤 도구를 골랐나'만 확인하는 실험
            result = await client.chat(
                [{"role": "user", "content": question}], tools=TOOLS, model=model
            )
            chosen = result.tool_calls[0].name if result.tool_calls else None
            correct += chosen == expected  # True는 1, False는 0으로 더해진다
            mark = "O" if chosen == expected else "X"
            print(f"{mark} {question} → {chosen} (기대: {expected})")
    print(f"{model}: {correct}/{len(SCENARIOS)}")


if __name__ == "__main__":
    # 실행할 때 모델 별칭을 줄 수 있다: uv run python scripts\select_test.py local
    asyncio.run(selection_rate(sys.argv[1] if len(sys.argv) > 1 else "fast"))