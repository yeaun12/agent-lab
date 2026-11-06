"""1.4 공급자 통합 LLM 클라이언트.

어느 공급자(Groq, Gemini, Ollama)를 부르든 내 코드는 항상
`await client.chat(messages, model="smart")` 한 가지 방식으로 부르고,
항상 같은 모양(ChatResult)의 결과를 받는다.
"""

import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()  # .env의 API 키를 환경 변수로 올린다

# 이 파일 위치(src/agent_lab/core/llm.py)에서 세 단계 위 = 프로젝트 폴더 → config/models.yaml
CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "models.yaml"


# ---------- 결과 모양 (공급자가 달라도 항상 이 모양으로 돌려준다) ----------
class Usage(BaseModel):
    prompt_tokens: int = 0  # 보낸 글의 토큰 수
    completion_tokens: int = 0  # 받은 답의 토큰 수


class ToolCall(BaseModel):
    id: str  # 도구 호출 번호. 결과를 돌려줄 때 같은 번호를 써야 한다 (1.5)
    name: str  # 부를 도구(함수) 이름
    arguments: str  # 인자. JSON 문자열이라 json.loads로 풀어 써야 한다
    # Gemini 3 계열이 붙여 주는 값(thought_signature). 다음 요청에 그대로 돌려줘야 도구 호출이 이어진다 (3.6)
    extra: dict | None = None


class ChatResult(BaseModel):
    text: str | None  # 답변 글. 도구만 부를 때는 None일 수 있다
    tool_calls: list[ToolCall] = Field(
        default_factory=list
    )  # 모델이 요청한 도구 호출들
    usage: Usage
    latency_ms: int  # 요청부터 응답까지 걸린 시간
    provider: str  # groq / gemini / ollama
    model: str  # 실제 모델 이름
    finish_reason: str | None  # stop(정상 끝), length(잘림), tool_calls(도구 요청)


# ---------- 내 예외 (공급자마다 다른 오류를 이 네 가지로 바꾼다) ----------
class LLMError(Exception):
    """LLM 호출 오류의 공통 부모. `except LLMError`로 전부 잡을 수 있다."""


class RateLimited(LLMError):
    """429: 요청 한도 초과. retry_after초 뒤에 다시 시도하면 된다 (3.1에서 사용)."""

    def __init__(self, retry_after: float | None, message: str):
        super().__init__(message)
        self.retry_after = retry_after


class BadRequest(LLMError):
    """400·401·403·404·422: 요청이 잘못됨 (키 오타, 모델 이름 오타 등). 다시 해도 안 된다."""


class RequestTooLarge(BadRequest):
    """413: 요청 하나가 너무 큼. Groq 무료 등급은 입력+출력이 TPM 8K를 넘으면 이 오류다 (3.6).
    줄여서 다시 보내거나 긴 컨텍스트 모델(long)로 보낸다."""

class ProviderError(LLMError):
    """5xx: 공급자 서버 문제. 잠시 뒤 재시도하거나 다른 공급자로 넘긴다 (3.2)."""


class LLMTimeout(LLMError):
    """정해 둔 시간 안에 응답이 오지 않음."""


def load_models(path: Path = CONFIG_PATH) -> dict:
    """models.yaml을 읽어 {별칭: 설정} 딕셔너리로 돌려준다."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def raise_for_status(r: httpx.Response) -> None:
    """응답 상태 코드를 보고 내 예외로 바꿔 던진다. 정상(2xx)이면 아무것도 안 한다."""
    if r.status_code == 429:
        retry_after = r.headers.get("retry-after")  # 몇 초 뒤에 다시 하라는 안내
        try:
            seconds = float(retry_after) if retry_after else None
        except ValueError:  # 숫자가 아닌 형식이면 모르는 것으로 둔다
            seconds = None
        raise RateLimited(seconds, r.text[:200])
    if r.status_code == 413:  # BadRequest보다 먼저 검사한다 (3.6에서 추가)
        raise RequestTooLarge(f"413: {r.text[:200]}")
    if r.status_code in (400, 401, 403, 404, 422):
        raise BadRequest(f"{r.status_code}: {r.text[:200]}")
    if r.status_code >= 500:
        raise ProviderError(f"{r.status_code}: {r.text[:200]}")


class LLMClient:
    def __init__(
        self, models: dict | None = None, timeout: float = 60.0, transport=None
    ):
        # models를 안 주면 config/models.yaml을 읽는다 (테스트에서는 직접 넣을 수 있다)
        self.models = models or load_models()
        # httpx 클라이언트는 하나만 만들어 계속 재사용한다 (1.1에서 배운 것)
        # transport: 테스트에서 가짜 서버를 끼워 넣을 때만 쓴다
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def aclose(self):
        await self._http.aclose()  # 다 쓰면 연결을 닫는다

    # async with LLMClient() as client: 로 쓰면 끝날 때 자동으로 닫힌다
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    def _target(self, alias: str):
        """별칭(smart 등)으로 (설정, 요청 주소, 헤더)를 만든다."""
        cfg = self.models[alias]  # 없는 별칭이면 KeyError로 바로 알 수 있다
        key_env = cfg.get("api_key_env")
        key = os.environ.get(key_env, "") if key_env else "ollama"  # Ollama는 키가 없다
        url = f"{cfg['base_url']}/chat/completions"
        return cfg, url, {"Authorization": f"Bearer {key}"}

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str = "smart",
        **options,
    ) -> ChatResult:
        """한 번 호출해서 ChatResult를 돌려준다. options에는 temperature, max_tokens 등을 넣는다."""
        cfg, url, headers = self._target(model)
        body = {"model": cfg["model"], "messages": messages, **options}
        if tools:  # 도구가 있을 때만 넣는다 (1.5)
            body["tools"] = tools
        start = time.perf_counter()
        try:
            r = await self._http.post(url, headers=headers, json=body)
        except httpx.TimeoutException as e:
            raise LLMTimeout(f"{model}: {e}") from e  # from e: 원래 오류도 함께 남긴다
        raise_for_status(r)
        data = r.json()
        choice = data["choices"][0]
        msg = choice["message"]
        # 공급자의 tool_calls 모양을 내 ToolCall 모양으로 바꾼다 (없으면 빈 목록)
        calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=tc["function"]["arguments"],
                extra=tc.get("extra_content"),
            )
            for tc in msg.get("tool_calls") or []
        ]
        usage = data.get("usage") or {}
        return ChatResult(
            text=msg.get("content"),
            tool_calls=calls,
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            ),
            latency_ms=round((time.perf_counter() - start) * 1000),
            provider=cfg["provider"],
            model=cfg["model"],
            finish_reason=choice.get("finish_reason"),
        )

    async def stream(
        self, messages: list[dict], model: str = "smart", **options
    ) -> AsyncIterator[str]:
        """답을 글자 조각 단위로 하나씩 내보낸다. 사용: async for piece in client.stream(...)"""
        cfg, url, headers = self._target(model)
        body = {"model": cfg["model"], "messages": messages, "stream": True, **options}
        try:
            async with self._http.stream("POST", url, headers=headers, json=body) as r:
                if r.status_code >= 400:
                    await r.aread()  # 오류 본문을 읽어 둬야 r.text를 쓸 수 있다
                    raise_for_status(r)
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: ") :]
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if chunk.get("choices"):
                        piece = chunk["choices"][0]["delta"].get("content")
                        if piece:
                            yield piece  # 받은 조각을 바로 내보낸다
        except httpx.TimeoutException as e:
            raise LLMTimeout(f"{model}: {e}") from e


class FakeLLM:
    """테스트용 가짜 클라이언트. 미리 넣어 둔 결과를 순서대로 돌려준다 (네트워크·한도 사용 없음)."""

    def __init__(self, replies: list[ChatResult]):
        self.replies = list(replies)  # 돌려줄 결과들
        self.calls: list[dict] = []  # 어떤 요청이 왔는지 기록 (테스트에서 확인용)

    async def chat(self, messages, tools=None, model="smart", **options) -> ChatResult:
        self.calls.append({"messages": messages, "tools": tools, "model": model})
        return self.replies.pop(0)  # 맨 앞 결과를 꺼내 준다

    @staticmethod
    def reply(
        text: str | None = None, tool_calls: list[ToolCall] | None = None
    ) -> ChatResult:
        """테스트에서 결과를 짧게 만들기 위한 도우미."""
        return ChatResult(
            text=text,
            tool_calls=tool_calls or [],
            usage=Usage(),
            latency_ms=0,
            provider="fake",
            model="fake",
            finish_reason="tool_calls" if tool_calls else "stop",
        )
