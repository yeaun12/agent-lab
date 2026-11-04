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
