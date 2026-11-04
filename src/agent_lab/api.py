"""1.2 FastAPI 기초: /health, /echo, /stream 세 엔드포인트."""

import asyncio
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_lab.core.settings import Settings, get_settings

# 웹 서버 앱 하나. 실행: uv run uvicorn agent_lab.api:app --reload
app = FastAPI(title="agent-lab")


# ---------- /health: 서버가 살아 있는지 확인 ----------
@app.get("/health")  # GET 방식으로 /health 주소에 오면 아래 함수가 실행된다
async def health(settings: Annotated[Settings, Depends(get_settings)]):
    # Annotated[타입, Depends(함수)]: FastAPI가 get_settings()를 대신 불러 settings에 넣어 준다 (의존성 주입)
    # '= Depends(...)'로 쓰는 옛 방식도 동작하지만 ruff가 경고(B008)해서 이 방식을 쓴다
    # 돌려주는 딕셔너리는 자동으로 JSON 응답이 된다. 키 값은 절대 응답에 넣지 않는다
    return {
        "status": "ok",
        "app": settings.app_name,
        "time": datetime.now().isoformat(timespec="seconds"),
    }


# ---------- /echo: 입력 검증 연습 ----------
class EchoIn(BaseModel):
    # 요청 본문(JSON)의 모양. 이 모양과 다르면 FastAPI가 자동으로 422 오류를 돌려준다
    text: str
    repeat: int = Field(1, ge=1, le=5)  # 기본값 1, 1 이상(ge) 5 이하(le)만 허용
    upper: bool = False  # True면 결과를 대문자로


class EchoOut(BaseModel):
    # 응답의 모양. response_model로 지정하면 /docs 화면에 응답 형식이 표시된다
    result: str


@app.post("/echo", response_model=EchoOut)  # POST 방식: 본문(JSON)을 받아서 처리
async def echo(body: EchoIn):
    # body에는 이미 검증을 통과한 값만 들어온다 (repeat=10이면 여기까지 오지 않는다)
    result = " ".join([body.text] * body.repeat)
    if body.upper:
        result = result.upper()
    return EchoOut(result=result)


# ---------- /stream: SSE로 한 단어씩 흘려보내기 ----------
WORDS = ["오늘은", "Fastapi", "를", "배웠다"]


async def word_stream():
    # yield가 있는 async 함수 = 값을 하나씩 내보내는 '흐름'(async generator)
    for word in WORDS:
        # SSE 형식: 'data: 내용' 다음에 빈 줄(\n\n)이 와야 한 덩어리로 인식된다
        yield f"data: {word}\n\n"
        # 0.3초 쉬었다 다음 단어 (쉬는 동안 서버는 다른 요청도 처리한다)
        await asyncio.sleep(1)
    yield "data: [DONE]\n\n"  # 끝났다는 표시. OpenAI 형식 스트리밍도 같은 방식이다


@app.get("/stream")
async def stream():
    # StreamingResponse: 응답을 한 번에 보내지 않고 word_stream()이 내보내는 대로 조금씩 보낸다
    return StreamingResponse(word_stream(), media_type="text/event-stream")
