"""1.6 구조화 출력: 최종 답을 정해진 JSON 모양으로 받기. 실행: uv run python scripts\\answer_demo.py"""

import asyncio
import json

from pydantic import BaseModel, Field, ValidationError

from agent_lab.core.llm import LLMClient


class Answer(BaseModel):
    summary: str  # 한두 문장 답
    confidence: float = Field(ge=0, le=1)  # 0~1 사이 확신도
    sources: list[str]  # 근거 (나중에 2단계에서 파일:줄 번호가 들어간다)
    keywords: list[str]


# 모델에게 원하는 모양을 알려 주는 지시. 스키마를 Pydantic에서 그대로 뽑아 붙인다
INSTRUCTION = (
    "Answer ONLY with a JSON object that matches this JSON Schema. No other text.\n"
    + json.dumps(Answer.model_json_schema(), ensure_ascii=False)
)


async def structured(
    client: LLMClient, question: str, model: str = "fast", tries: int = 2
) -> Answer | None:
    """JSON 모양으로 답을 받아 검증한다. 틀리면 오류를 알려 주고 한 번 더 묻는다."""
    messages = [
        {"role": "system", "content": INSTRUCTION},
        {"role": "user", "content": question},
    ]
    for _ in range(tries):
        # response_format json_object: 'JSON으로만 답하라'는 공급자 기능 (Groq, Gemini, Ollama 지원)
        result = await client.chat(
            messages, model=model, response_format={"type": "json_object"}
        )
        try:
            return Answer.model_validate_json(result.text or "")  # 모양까지 맞아야 통과
        except ValidationError as e:
            # 틀린 답과 이유를 대화에 붙여 다시 요청한다
            messages += [
                {"role": "assistant", "content": result.text or ""},
                {
                    "role": "user",
                    "content": f"형식 오류: {e.errors()[0]['msg']}. 스키마에 맞게 다시 답하라.",
                },
            ]
    return None  # 끝내 실패


async def main():
    async with LLMClient() as client:
        answer = await structured(
            client, "파이썬에서 리스트와 튜플의 차이는?", model="fast"
        )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())