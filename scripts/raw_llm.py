"""1.3 LLM API를 원시 HTTP로 호출해 보기. 실행: uv run python scripts\\raw_llm.py"""

import json
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()  # 프로젝트 폴더의 .env를 읽어 환경 변수로 올린다 (키를 코드에 쓰지 않기 위해)

# 공급자별 주소·키 이름·모델. 모두 OpenAI 호환 형식이라 주소만 바꾸면 같은 코드로 부를 수 있다
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-20b"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "GEMINI_API_KEY",
        "gemini-3.5-flash-lite",
    ),
    "ollama": ("http://localhost:11434/v1", None, "llama3.2:3b"),  # 로컬이라 키가 없다
}

PROVIDER = "gemini"  # ← 여기만 바꾸면 다른 공급자로 같은 실험을 한다


def setup(provider):
    """공급자 이름으로 (요청 주소, 헤더, 모델 이름)을 만든다."""
    base_url, key_env, model = PROVIDERS[provider]
    # 키가 필요 없는 Ollama는 아무 문자열이나 넣는다 (헤더 모양만 맞추기)
    key = os.environ[key_env] if key_env else "ollama"
    headers = {"Authorization": f"Bearer {key}"}  # 키는 print하지 않는다
    return f"{base_url}/chat/completions", headers, model


def call_once(url, headers, model, messages, **options):
    """한 번 호출해서 (응답 JSON, 걸린 ms)를 돌려준다. options에는 temperature 등을 넣는다."""
    start = time.perf_counter()
    r = httpx.post(
        url,
        headers=headers,
        json={
            "model": model,
            "messages": messages,
            **options,
        },  # **: 옵션을 본문에 펼쳐 넣기
        timeout=60,  # 로컬 모델은 느릴 수 있어 넉넉하게
    )
    r.raise_for_status()  # 4xx·5xx면 여기서 예외가 나서 원인을 바로 볼 수 있다
    return r.json(), round((time.perf_counter() - start) * 1000)


def measure_ttft(url, headers, model, messages):
    """stream=True로 받아서 첫 글자 조각이 올 때까지 걸린 시간(TTFT)을 잰다."""
    start = time.perf_counter()
    ttft = None
    pieces = []
    body = {"model": model, "messages": messages, "stream": True}
    # httpx.stream: 응답을 한 번에 받지 않고 줄 단위로 흘려 받는다
    with httpx.stream("POST", url, headers=headers, json=body, timeout=60) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "):  # 빈 줄 등은 건너뛴다
                continue
            data = line[len("data: ") :]
            if data == "[DONE]":  # 끝 표시
                break
            chunk = json.loads(data)
            if not chunk.get("choices"):  # 내용 없는 조각(사용량 정보 등)은 건너뛴다
                continue
            delta = chunk["choices"][0]["delta"].get("content") or ""
            if delta and ttft is None:  # 처음으로 글자가 온 순간
                ttft = round((time.perf_counter() - start) * 1000)
            pieces.append(delta)
    return ttft, "".join(pieces)


if __name__ == "__main__":
    url, headers, model = setup(PROVIDER)
    question = [{"role": "user", "content": "한국에서 가장 많이 쓰는 인사말 해줘."}]

    # ① 첫 호출: 답변, 토큰 사용량, 걸린 시간
    data, ms = call_once(url, headers, model, question)
    print("답변:", data["choices"][0]["message"]["content"])
    print("토큰:", data["usage"], f"/ {ms} ms")

    # ② system 메시지로 말투 바꾸기 (같은 질문, 다른 지시)
    styled = [{"role": "system", "content": "Answer in exactly one word."}, *question]
    data, _ = call_once(url, headers, model, styled)
    print("한 단어로:", data["choices"][0]["message"]["content"])

    # ③ 첫 토큰까지 시간 (TTFT)
    ttft, text = measure_ttft(url, headers, model, question)
    print(f"TTFT: {ttft} ms / 스트리밍으로 받은 답: {text[:40]}")

    # ④ max_tokens를 아주 작게 → finish_reason이 'length'(잘림)
    data, _ = call_once(url, headers, model, question, max_tokens=5)
    print("max_tokens=5 →", data["choices"][0]["finish_reason"])

for _ in range(5):
    print(
        call_once(url, headers, model, question, temperature=1)[0]["choices"][0][
            "message"
        ]["content"]
    )
