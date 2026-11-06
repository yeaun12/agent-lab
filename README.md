# agent-lab

무료 LLM과 로컬 모델로 직접 만드는 AI 에이전트 실습 저장소.
첫 에이전트는 repo-pilot(코드베이스 Q&A + GitHub PR 리뷰).

## 목표
- LLM 주변 시스템(도구 호출, 메모리, 평가, 가드레일, 배포)을 프레임워크 없이 직접 만들고 수치로 증명한다.
- 겪은 실패는 [FAILURES.md](FAILURES.md)에 기록한다.

## 현재 진행 단계
- 1단계 환경 세팅 완료
- 2단계 기초 완료: asyncio, FastAPI, 공급자 공통 LLMClient, 도구 호출 순환, Pydantic 스키마와 검증 재시도
- 3단계 코드베이스 Q&A 완료: httpx 저장소 수집·청킹·임베딩 색인(Qdrant), 하이브리드 검색, 직접 만든 ReAct 루프, SSE로 단계를 보여 주는 웹 화면

> 단계 번호를 2026-11-05에 0~9에서 1~10으로 바꿨다. 그 전에 쓴 커밋 메시지와 문서(FAILURES.md, docs/notes)의 번호는 1을 더하면 지금 번호다(예: 1.5 → 2.5, 1단계 → 2단계).

## 2단계(기초)에서 측정한 것
| 항목 | 결과 |
|---|---|
| 비동기 vs 동기 (URL 20개, 동시성 5) | 5.4초 vs 21.4초 |
| 첫 글자까지 시간(TTFT) | Groq gpt-oss-20b 약 0.9~1.2초, Gemini 3.5 Flash Lite 약 1.2초 |
| 도구 선택률 (질문 10개) | fast 10/10, smart 10/10, local(llama3.2:3b) 6/10 |

## 3단계(코드베이스 Q&A)에서 측정한 것
대상: [httpx](https://github.com/encode/httpx) (96개 파일, 23,361줄)

| 항목 | 결과 |
|---|---|
| 청크 수 | 고정 크기 505개, 함수·클래스 단위 1,660개 |
| 색인 (CPU 임베딩) | 전체 약 14분, 파일 하나 바꾼 증분 색인 8.5초 |
| 검색 recall@5 (개발용 20문항) | 벡터 10/20 → 테스트 코드 제외 11/20 → 질문을 영어로 바꾸기까지 **20/20** |
| 검색 recall@5 (봉인 10문항, 한 번만 실행) | 5/10 → 6/10 → **8/10** |
| 에이전트 파일 일치 (10문항, fast) | ReAct 9/10, 계획-실행 10/10 |
| 질문당 토큰 | ReAct 6,700, 계획-실행 9,229 → fast 하루 약 30문항 |

어디까지 믿을 수 있는지는 [docs/trust.md](docs/trust.md), 무료 한도 계산은 [docs/budget.md](docs/budget.md)에 있다.
자세한 내용은 [docs/notes](docs/notes)와 [docs/providers.md](docs/providers.md)에 있다.

## 폴더 구조
- `src/agent_lab/core`: 공통 부품 (설정, LLM 클라이언트, 도구)
- `src/agent_lab/agents/repo_pilot`: 첫 에이전트 전용 부품
- `scripts/`: 실험 스크립트 (asyncio, 원시 호출, 도구 호출, 선택률, 구조화 출력)
- `tests/`: pytest 테스트 (`live` 표시가 붙은 것은 실제 모델을 부른다)
- `config/models.yaml`: 모델 별칭 (fast, smart, long, local)
- `docs/`: 공급자 비교, 역량 정리 노트
- `evals/repo_pilot/`: 검색·에이전트 평가 질문(개발용 20, 봉인 10)과 결과
- `data/`: clone한 저장소와 색인 (Git에 올리지 않음, 다시 만들 수 있음)

## 실행 방법
```powershell
uv sync                                   # 의존성 설치
copy .env.example .env                    # 키 이름만 있는 파일을 복사한 뒤 값을 채운다
uv run pytest -m "not live"               # 모델 없이 도는 테스트
uv run pytest -m live                     # 실제 모델 호출 테스트 (Ollama 켜기, .env 키 필요)
uv run uvicorn agent_lab.api:app --reload # API 서버, http://127.0.0.1:8000/docs
uv run python scripts/tool_demo.py        # 도구 호출 순환 데모
uv run python scripts/select_test.py fast # 모델별 도구 선택률 (fast / smart / local)

# 3단계 repo-pilot (Ollama 켜기)
git clone --depth 1 https://github.com/encode/httpx.git data/repos/httpx
uv run python scripts/build_index.py httpx B          # 색인 (CPU로 약 14분)
uv run python scripts/eval_retrieval.py               # 검색 품질 측정
uv run python scripts/ask.py "기본 타임아웃은 몇 초야?" fast   # 에이전트에게 질문
uv run uvicorn agent_lab.api:app --reload             # http://127.0.0.1:8000 질문 화면
```
