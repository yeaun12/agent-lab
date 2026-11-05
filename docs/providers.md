# LLM 공급자 비교 (무료 등급)



[0.3 로컬 모델 측정 - 2026-11-04, CPU 전용(GPU 끔)]
| 모델 | 크기 | 파라미터 | 양자화 | tokens/s | 컨텍스트 | 기능 |
|---|---|---|---|---|---|---|
| llama3.2:3b | (ollama list 확인) | 3.2B | Q4_K_M | 11.1 | 131,072 | tools |
| qwen3.5:4b | 3.3GB | 4.2B | Q4_K_M | 6.8 | 262,144 | tools, thinking(기본 on), vision |
| nomic-embed-text | 274MB | - | - | 임베딩 768차원 | - | - |

■ 한도 표
| 공급자 | 모델 | RPM | RPD | TPM | 컨텍스트 | tool calling |
|---|---|---|---|---|---|---|
| Groq | openai/gpt-oss-120b | 30 | 1K | 8K | 131,072 / 출력 65,536 | 지원 (병렬 X, JSON O) |
| Groq | openai/gpt-oss-20b | 30 | 1K | 8K | 131,072 / 출력 65,536 | 지원 (병렬 X, JSON O) |
| Groq | qwen/qwen3.8-27b | 30 | 1K | 8K | 131,072 / 출력 16,384 | 지원 (병렬 O, JSON O), Preview |
| Gemini | gemini-3.5-flash-lite | 15 | 500 | 250K | 1,048,576 / 출력 65,536 | 지원 (Structured outputs O) |
| Gemini | gemini-3.8-flash | 5 | 20 | 250K | 1,048,576 / 출력 65,536 | 지원 (Structured outputs O) |
| OpenRouter | (:free 모델) | 20 | 50 | 미표기 | 모델별 | 모델별 |
| Ollama | llama3.2:3b | 없음 | 없음 | 없음 | 131,072 | 지원 |
| Ollama | qwen3.5:4b | 없음 | 없음 | 없음 | 262,144 | 지원 |

## 1.3·1.4에서 새로 안 것 (2026-11-05 측정, `scripts/raw_llm.py` 방식의 원시 호출)

질문: "한국에서 가장 많이 쓰는 인사말 해줘."

### 첫 글자까지 시간 (TTFT, stream=True)
| 공급자 | 모델 | TTFT |
|---|---|---|
| Groq | openai/gpt-oss-20b | 883 ms (이전 측정 약 1,175 ms) |
| Gemini | gemini-3.5-flash-lite | 1,230 ms |

- 측정할 때마다 수백 ms씩 달라진다. 한 번 잰 값이 아니라 범위로 본다.
- 전체 응답 시간보다 TTFT가 체감 속도를 정한다. 그래서 1.2에서 SSE 스트리밍을 만들었다.

### 요청 한도 헤더
Groq는 **매 응답**에 남은 한도를 헤더로 알려 준다.

| 헤더 | 값(예) | 뜻 |
|---|---|---|
| x-ratelimit-limit-requests | 1000 | 하루 요청 한도 (RPD) |
| x-ratelimit-remaining-requests | 999 | 오늘 남은 요청 |
| x-ratelimit-reset-requests | 1m26.4s | 요청 한도가 회복되기까지 |
| x-ratelimit-limit-tokens | 8000 | 분당 토큰 한도 (TPM) |
| x-ratelimit-remaining-tokens | 7313 | 이번 1분에 남은 토큰 |
| x-ratelimit-reset-tokens | 5.152s | 토큰 한도가 회복되기까지 |

- 한도를 넘으면 429와 `retry-after`(몇 초 뒤 다시)가 온다. `src/agent_lab/core/llm.py`는 이 값을 `RateLimited.retry_after`에 담는다.
- Gemini(OpenAI 호환 주소)는 응답에 한도 헤더가 **없었다**. 남은 한도를 알 수 없으니, 3.1에서 내 쪽에서 요청 수를 세는 제한기가 필요하다.

### reasoning 토큰 (보이지 않는 생각 토큰)
| 공급자 | 입력 | 출력 | 그중 reasoning |
|---|---|---|---|
| Groq gpt-oss-20b | 83 | 416 | 146 |
| Gemini 3.5 Flash Lite | 11 | 447 | (따로 표시 안 됨) |

- gpt-oss는 답을 쓰기 전에 생각 토큰을 만든다. 이 토큰은 답에는 안 보이지만 출력 토큰과 TPM 한도에 **포함된다**. 이 예에서는 출력의 약 35%였다.
- 그래서 `max_tokens`를 너무 작게 주면 생각만 하다 잘린다. 1.3에서 `max_tokens=5` → `finish_reason: "length"`를 확인했다.
- 같은 질문인데 입력 토큰이 Groq 83, Gemini 11로 다르다. 공급자마다 시스템 문구와 토크나이저가 달라서, 토큰 수는 공급자끼리 직접 비교하지 않는다.
- Groq usage에는 `queue_time`(대기), `prompt_time`, `completion_time`도 들어 있다. 느릴 때 원인이 대기인지 생성인지 나눠 볼 수 있다.
