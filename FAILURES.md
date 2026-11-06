# FAILURES.md

겪은 실패를 '증상 · 재현 · 원인 · 수정 · 결과 · 교훈'으로 남긴다.

## [2026-11-04] 0.5 · .env.example에 진짜 키를 넣을 뻔함
- 증상: 값을 비워야 하는 .env.example에 API 키 3개를 넣고 저장함
- 재현: .env.example을 먼저 만들고 그 파일에 바로 키를 붙여 넣음
- 원인: .env와 .env.example의 역할(비밀 값 / 키 이름 목록)을 헷갈림
- 수정: 커밋 전에 발견 → 파일 이름을 .env로 바꾸고 빈 .env.example을 다시 만듦
- 결과: 커밋·원격 저장소가 없던 상태라 키 노출 없음
- 교훈: 비밀 값을 다룬 직후, 커밋 전에 git status와 파일 내용을 한 번 더 본다

## [2026-11-04] 1.1 · asyncio.run을 두 번 감싸 ValueError
- 증상: `fetch_all`을 실행하자 `ValueError: a coroutine was expected`가 남
- 재현: 실행부를 `asyncio.run(asyncio.run(fetch_all(URLS)))`처럼 두 번 감쌈
- 원인: 안쪽 `asyncio.run`이 이미 실행을 끝내고 결과(리스트)를 돌려줌 → 바깥 `asyncio.run`은 코루틴이 아닌 리스트를 받음
- 수정: `asyncio.run(fetch_all(URLS))` 한 번만 남김
- 결과: 비동기 5.4초 vs 동기 21.4초(URL 20개, 동시성 5) 측정 성공
- 교훈: `asyncio.run`은 프로그램 진입점에서 한 번만 쓴다. 안쪽에서는 `await`

## [2026-11-04] 1.1 · 함수를 고쳤는데 실행 결과가 그대로
- 증상: `fetch_one`에 bytes·ok 필드를 추가했는데 출력이 바뀌지 않음
- 재현: 고친 함수는 비동기 버전인데, `if __name__ == "__main__":` 아래에서는 동기 버전만 호출하고 있었음
- 원인: 파일을 실행하면 맨 아래 실행부에 적힌 함수만 돈다. 고친 함수가 호출되지 않았음
- 수정: 실행부에서 비동기 버전을 호출하도록 바꿈
- 결과: 결과에 bytes·ok, 오류 개수 요약 줄이 나옴
- 교훈: 결과가 안 바뀌면 코드보다 먼저 "이 함수가 실제로 호출되는가"를 확인한다

## [2026-11-05] 1.5 · 테스트 폴더 이름 오타로 pytest 수집 오류
- 증상: `uv run pytest -m "not live"`가 `ERROR collecting tests/test_tools.py`, `import file mismatch`로 멈춤
- 재현: 1.5에서 `test\test_tools.py`(s 없음)를 만들고, 1.6에서 `tests\test_tools.py`(s 있음)를 따로 만듦
- 원인: pytest가 같은 이름의 모듈 `test_tools`를 두 폴더에서 발견해 어느 쪽인지 정하지 못함. 같은 실수로 `scripts\tools_demo.py`와 `tool_demo.py`도 둘 다 있었음
- 수정: 잘못 만든 `test` 폴더와 `scripts\tools_demo.py` 삭제
- 결과: 18 passed, 2 deselected
- 교훈: 파일을 만들 때 경로를 손으로 치지 않고 안내의 경로를 복사한다. 낯선 수집 오류가 나면 `git status`로 의도하지 않은 파일부터 본다

## [2026-11-05] 1.5 · 작은 모델이 잡담에도 도구를 부름 (미해결)
- 증상: local(llama3.2:3b)의 도구 선택률이 6/10. 잡담 4개 모두 도구를 부름('안녕?' → get_weather, '고마워!' → calculate 등)
- 재현: `uv run python scripts\select_test.py local`
- 원인(추정): 작은 모델은 도구 목록이 주어지면 쓸 필요가 없어도 쓰려는 경향이 있음. description에는 "언제 쓰는지"만 있고 "언제 쓰지 않는지"가 없음
- 수정: calculate 설명에 "반드시 이 도구를 쓴다"를 넣었지만 6/10 그대로(이 문장은 과소 호출용이라 과잉 호출에는 효과 없음)
- 결과: 도구 선택은 fast/smart에 맡기고, local은 도구 없는 작업(임베딩·분류·요약)에 쓰기로 결정
- 교훈: 선택률 숫자 하나보다 "어느 쪽으로 틀렸나"(과소 호출 / 과잉 호출)를 나눠 봐야 고칠 방법이 정해진다. 다음 시도: 시스템 프롬프트에 "도구가 필요 없으면 바로 답한다" 넣기

## [2026-11-05] 1.5 · 같은 설정인데 선택률이 8/10과 10/10으로 다름
- 증상: fast가 고치기 전 calculate 설명으로 한 번은 8/10, 다른 실행에서는 10/10
- 재현: 같은 `select_test.py fast`를 다른 시간에 실행
- 원인: 모델 응답이 매번 조금씩 달라짐(실행 변동). 10문항이라 한 문제가 10%p를 움직임
- 수정: 없음(측정 방법의 한계로 기록)
- 결과: "설명을 고쳐서 8→10이 됐다"는 한 번의 실행만으로는 단정할 수 없음
- 교훈: 작은 실험은 여러 번 돌려 범위를 보고, 결과는 8/10처럼 개수와 함께 적는다. 5단계 평가에서 반복 실행으로 다룬다

## [2026-11-06] 3.4 · 한국어 질문에서 벡터 검색이 정답을 못 찾음 (q04)
- 증상: q04 "리다이렉트가 너무 많으면 어떤 예외가 나나?"의 B-벡터 상위 5개에 정답 파일(httpx/_exceptions.py, httpx/_client.py)이 하나도 없음. 유사도가 0.541~0.551로 거의 같음(1위 CHANGELOG.md)
- 재현: `uv run python scripts\search.py "리다이렉트가 너무 많으면 어떤 예외가 나나?" httpx_B_p`
- 원인: 질문은 한국어인데 코드와 임베딩 모델(nomic-embed-text)은 영어 위주라 질문 벡터가 코드 벡터와 잘 맞지 않음
- 확인: 같은 뜻을 영어로 바꾸면 결과가 확 달라짐
  - "what exception is raised when there are too many redirects" → `_exceptions.py:249` TooManyRedirects 1위(0.774), `_client.py`도 5위 안
  - "TooManyRedirects exception max_redirects" → 1위 0.834, 정답 파일 둘이 1·2위
- 수정: 3.4 고쳐 보기 ②(검색 전에 fast 모델로 질문을 영어 검색어로 바꿈) + ①(tests/ 결과 빼기)
- 결과: B-하이브리드 recall@5 10/20 → 20/20 (번역 모델 long, 2026-11-06). 봉인 질문에서도 5/10 → 8/10
- 교훈: 검색 방식을 바꾸기 전에 질문과 문서의 언어부터 맞춘다. 유사도가 다 비슷하게 낮으면(0.55 근처) "가까운 게 없다"는 신호다. 코드 이름이 질문에 들어가면 청크 헤더(`symbol:`)와 직접 맞아 더 정확해진다

## [2026-11-05] 3.1 · 실험용 설정을 되돌리지 않아 가장 중요한 파일이 색인에서 빠질 뻔함
- 증상: `chunk_stats.py`가 기대값(방식 A 505개, B 1,660개)보다 적은 A 439개, B 1,373개를 냄. 예시 출력도 `httpx/_client.py` 대신 `tests/client/test_async_client.py`가 나옴
- 재현: 3.1 고쳐 보기에서 `ingest.py`의 `MAX_BYTES = 50_000`, `LANG`에 `.txt` 추가를 한 채로 3.2 진행
- 원인: 50KB 상한 때문에 `httpx/_client.py`(67KB)와 `CHANGELOG.md`(54KB)가 수집에서 빠짐. 고쳐 보기 뒤 원래대로 되돌리지 않음
- 수정: `MAX_BYTES = 1_000_000`, `LANG` 원래대로 → `repo_stats.py`가 96개 파일로 돌아온 것 확인 후 색인
- 결과: 색인 3개 모두 96개 파일, `_client.py` 포함
- 교훈: 실험용으로 바꾼 값은 실험이 끝나면 바로 되돌리고, 다음 단계 전에 기준 숫자(파일 수)로 확인한다. 숫자가 기대값과 다르면 앞 단계의 설정부터 의심한다

## [2026-11-06] 3.1 · .gitignore에 data/를 넣기 전에 git add를 해 버림
- 증상: `git add .` 중 `warning: adding embedded git repository: data/repos/httpx`. `git status`에 `A  data/qdrant/…`, `Am data/repos/httpx`가 보임(38MB)
- 재현: `.gitignore`에 `data/`를 저장하기 전에 `git add .`
- 원인: 무시 규칙이 없으니 clone한 httpx(안에 자기 `.git`이 있음)와 색인 파일이 모두 커밋 목록에 올라감. 목록에 올라간 파일은 `git check-ignore`도 무시 대상으로 보지 않음
- 수정: `.gitignore`에 `data/` 추가 → `git rm -r --cached data`는 httpx 내부 `.git` 때문에 `staged content different` 오류로 거절 → `git restore --staged data`로 목록에서만 뺌(파일은 그대로)
- 결과: `git check-ignore -v data/repos/httpx` → `.gitignore:13:data/`, 커밋 전이라 원격 노출 없음
- 교훈: 큰 데이터나 다른 저장소를 받기 전에 `.gitignore`부터 넣고, `git add .` 전에 `git status`를 본다

## [2026-11-06] 3.4 · 무료 한도에 연달아 걸림 (Groq 하루 한도, Gemini 분당 한도)
- 증상: ① `eval_retrieval.py`가 `RateLimited … tokens per day (TPD): Limit 200000, Used 199703`로 멈춤 ② 번역 모델을 long(Gemini)으로 바꾸자 `429 You exceeded your current quota`
- 재현: 같은 날 `agent_eval.py`를 react·plan·plan으로 세 번 돌린 뒤 `eval_retrieval.py` 실행
- 원인: ① 에이전트 실험 한 번에 fast 토큰 약 6.7만~9.2만을 써서 하루 200K를 넘김 ② Gemini 무료는 분당 15회인데 질문 20개를 쉬지 않고 연달아 보냄. 메시지는 하루 한도처럼 보였지만 1분 뒤 1회 호출은 정상이었음
- 수정: 번역 모델을 long으로 바꾸고 `to_english`에 호출마다 `await asyncio.sleep(4)` 추가. 번역 모델이 바뀌었으니 개발용 점수도 같은 모델로 다시 잼
- 결과: 개발용 20/20, 봉인 8/10 측정 완료
- 교훈: 하루 예산을 먼저 계산하고(docs/budget.md) 실험을 나눈다. 429는 분당·하루 중 어느 한도인지 먼저 확인한다(분당이면 기다리면 되고, 하루면 다른 공급자로)
