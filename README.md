# agent-lab

무료 LLM과 로컬 모델로 직접 만드는 AI 에이전트 실습 저장소.
첫 에이전트는 repo-pilot(코드베이스 Q&A + GitHub PR 리뷰).

## 목표
- LLM 주변 시스템(도구 호출, 메모리, 평가, 가드레일, 배포)을 프레임워크 없이 직접 만들고 수치로 증명한다.
- 겪은 실패는 [FAILURES.md](FAILURES.md)에 기록한다.

## 현재 진행 단계
- 0단계 환경 세팅 완료
- 1단계 기초 완료: asyncio, FastAPI, 공급자 공통 LLMClient, 도구 호출 순환, Pydantic 스키마와 검증 재시도

## 1단계에서 측정한 것
| 항목 | 결과 |
|---|---|
| 비동기 vs 동기 (URL 20개, 동시성 5) | 5.4초 vs 21.4초 |
| 첫 글자까지 시간(TTFT) | Groq gpt-oss-20b 약 0.9~1.2초, Gemini 3.5 Flash Lite 약 1.2초 |
| 도구 선택률 (질문 10개) | fast 10/10, smart 10/10, local(llama3.2:3b) 6/10 |

자세한 내용은 [docs/notes](docs/notes)와 [docs/providers.md](docs/providers.md)에 있다.

## 폴더 구조
- `src/agent_lab/core`: 공통 부품 (설정, LLM 클라이언트, 도구)
- `src/agent_lab/agents/repo_pilot`: 첫 에이전트 전용 부품
- `scripts/`: 실험 스크립트 (asyncio, 원시 호출, 도구 호출, 선택률, 구조화 출력)
- `tests/`: pytest 테스트 (`live` 표시가 붙은 것은 실제 모델을 부른다)
- `config/models.yaml`: 모델 별칭 (fast, smart, local)
- `docs/`: 공급자 비교, 역량 정리 노트
- `evals/`: 에이전트별 평가 질문 (2단계부터)

## 실행 방법
```powershell
uv sync                                   # 의존성 설치
copy .env.example .env                    # 키 이름만 있는 파일을 복사한 뒤 값을 채운다
uv run pytest -m "not live"               # 모델 없이 도는 테스트
uv run pytest -m live                     # 실제 모델 호출 테스트 (Ollama 켜기, .env 키 필요)
uv run uvicorn agent_lab.api:app --reload # API 서버, http://127.0.0.1:8000/docs
uv run python scripts/tool_demo.py        # 도구 호출 순환 데모
uv run python scripts/select_test.py fast # 모델별 도구 선택률 (fast / smart / local)
```
