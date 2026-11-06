# Q3. ReAct 루프는 어떻게 동작하나

## 한 문장
모델이 다음 행동(어떤 도구를 어떤 인자로)을 고르고 → 코드가 그 도구를 실행하고 → 결과를 대화에 붙여 다시 묻는 것을, 모델이 "이제 답할 수 있다"고 판단할 때까지 반복한다.
ReAct = Reason(생각) + Act(행동). 2.5의 도구 호출 순환과 같은 구조에, 인용 규칙·단계 상한·한도 대응을 더한 것이다.

## 내 로그로 보기 (scripts/ask.py)
`uv run python scripts\ask.py "리다이렉트가 너무 많으면 어떤 예외가 나나?" long` (2026-11-06)

```
[1] O search_code({"query":"TooManyRedirects"})  780토큰 3996ms
    → httpx/_exceptions.py:249-252 [class] TooManyRedirects
[2] O read_file({"path":"httpx/_exceptions.py","start_line":245,"end_line":255})  1321토큰 836ms
    → httpx/_exceptions.py:245-255

답 (done, 모델 long, 호출 3회, 3658토큰):
HTTPX에서 리다이렉트가 너무 많이 발생하면 `TooManyRedirects` 예외가 발생한다(httpx/_exceptions.py:249).
이 예외는 `RequestError`를 상속받아 정의된다(httpx/_exceptions.py:249). ...
```

한 바퀴씩 보면:
1. **생각 → 행동**: 질문은 한국어였지만 모델이 스스로 코드 이름 `TooManyRedirects`를 검색어로 골랐다(3.4에서 본 "영어·코드 이름이 검색에 유리하다"를 모델이 알아서 함)
2. **관찰**: 검색 결과 1위가 `_exceptions.py:249`
3. **생각 → 행동**: 검색 미리 보기만으로 답하지 않고, 근거를 확인하려고 그 줄 주변을 `read_file`로 열었다
4. **관찰 → 끝**: 확인할 것이 다 됐다고 판단하고 도구 없이 답했다(`done`). 모델 호출 3회 = 도구 2번 + 답 1번

## 대화 목록이 자라는 모양
| 순서 | 역할 | 내용 |
|---|---|---|
| ① | system | 규칙(추측 금지, `경로:줄` 인용, 못 찾으면 '찾지 못함') |
| ② | user | 질문 |
| ③ | assistant | tool_calls=[search_code(TooManyRedirects)] |
| ④ | tool | `httpx/_exceptions.py:249-252 …` |
| ⑤ | assistant | tool_calls=[read_file(_exceptions.py, 245~255)] |
| ⑥ | tool | `249: class TooManyRedirects(RequestError): …` |
| ⑦ | assistant | 최종 답 (도구 호출 없음) → 끝 |

매 호출마다 이 목록 전체를 다시 보내서, 단계가 늘수록 토큰이 커진다. 그래서 6K 토큰을 넘으면 오래된 도구 결과를 한 줄로 줄인다(Groq 무료는 요청 하나가 8K를 넘으면 413).

## 내 코드에서 어디인가
| 역할 | 위치 |
|---|---|
| 루프 | `src/agent_lab/agents/repo_pilot/agent.py`의 `run_events()` |
| 끝내는 조건 | 모델이 도구를 부르지 않으면 `answer` 이벤트로 끝 |
| 무한 반복 방지 | `max_steps=8` → 넘으면 `flatten()`으로 '질문 + 확인한 내용'만 남겨 도구 없이 부분 답 |
| 한도·형식 오류 대응 | `call_model()`: 분당 429는 기다림, 하루 429와 413은 long(Gemini)으로, Groq 도구 형식 400은 무엇이 틀렸는지 알려 주고 다시 |
| 도구 | `src/agent_lab/agents/repo_pilot/tools.py`의 `RepoToolbox` (search_code, read_file, list_dir, grep) |

## 측정 (3.6, fast, 개발용 질문 10개)
| 항목 | ReAct | 계획-실행 |
|---|---|---|
| 파일 일치 | 9/10 | 10/10 |
| 근거 타당성 | 6.3에서 채점 | 6.3에서 채점 |
| 평균 단계 | 3.1 | 3.9 |
| 평균 호출 | 4.1회 | 4.9회 |
| 질문당 토큰 | 6,700 | 9,229 |
| max_steps 도달 | 1건 | 2건 |

## 실패 사례
- **q01 "연결 재시도(retries)는 어디서 설정하나?"**: ReAct가 8단계를 다 쓰고도 인용 없이 "httpx에는 재시도 옵션이 없다"고 답했다. 실제로는 `httpx/_transports/default.py`의 `HTTPTransport(retries=...)`가 있다. 계획-실행은 같은 질문에서 `default.py`를 찾았다. → 단계가 많다고 정답에 가까워지는 게 아니라, 틀린 방향으로 계속 찾을 수도 있다.
- **읽지 않은 파일을 인용함**: 위 로그의 답 마지막 문장은 `tests/client/test_redirects.py:252, 260`을 근거로 댔지만, 에이전트가 실제로 연 파일은 `_exceptions.py`뿐이다. 검색 결과 미리 보기(첫 몇 줄)만 보고 인용한 것으로 보인다. → "파일을 인용했다(file_match)"와 "그 줄을 확인했다(근거 타당성)"는 다르다. 6.3에서 사람 채점으로 이런 경우를 센다.

## 정리
ReAct의 핵심은 **다음 행동을 코드가 아니라 모델이 정한다**는 것이다. 그래서 유연하지만, 같은 질문에도 경로와 비용이 매번 달라지고 틀린 방향으로 갈 수도 있다. 그걸 붙잡아 두는 장치가 단계 상한, 토큰 예산, 인용 규칙이고, 실제로 잘 되는지는 측정(파일 일치, 근거 타당성, 토큰)으로 확인한다.
