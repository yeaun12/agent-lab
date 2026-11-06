"""3.4 검색 품질 측정. 실행: uv run python scripts\\eval_retrieval.py
봉인 질문은 --split holdout을 붙였을 때만 돈다 (3.8에서 한 번만)."""
import asyncio
import json
import sys
from pathlib import Path

from agent_lab.agents.repo_pilot.index import search
from agent_lab.agents.repo_pilot.retrieval import bm25_search, hybrid_search
from agent_lab.core.llm import LLMClient

REPO = "httpx"
EVALS = Path(__file__).resolve().parents[1] / "evals" / "repo_pilot"
split = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else "dev"
questions = [json.loads(line) for line in (EVALS / f"{split}_qa.jsonl").read_text(encoding="utf-8").splitlines() if line]

async def to_english(texts: list[str]) -> list[str]:
    """질문을 영어 코드 검색어로 바꾼다. 임베딩 모델(nomic)과 코드가 영어라 한국어 질문이 불리하다."""
    rule = "Rewrite the user's question about the httpx Python library as a short English code-search query. Include likely identifiers. Output only the query."
    out = []
    async with LLMClient() as client:
        for t in texts:
            r = await client.chat([{"role": "system", "content": rule}, {"role": "user", "content": t}], model="long")
            out.append((r.text or t).strip())
            await asyncio.sleep(4)
    return out


EN = dict(zip([q["question"] for q in questions], asyncio.run(to_english([q["question"] for q in questions]))))

# 비교할 조합: 이름 → (질문을 받아 결과 목록을 돌려주는 함수)
SETUPS = {
    "A-벡터": lambda q: search(q, f"{REPO}_A_p", k=5),
    "B-벡터": lambda q: search(q, f"{REPO}_B_p", k=5),
    "B-벡터(접두어 없음)": lambda q: search(q, f"{REPO}_B", k=5),
    "B-BM25": lambda q: bm25_search(q, REPO, "B", k=5),
    "B-하이브리드": lambda q: hybrid_search(q, REPO, "B", f"{REPO}_B_p", k=5),
    "B-하이브리드(테스트 제외)": lambda q: hybrid_search(q, REPO, "B", f"{REPO}_B_p", k=5, drop_tests=True),
    "B-하이브리드(영어+테스트 제외)": lambda q: hybrid_search(EN[q], REPO, "B", f"{REPO}_B_p", k=5, drop_tests=True),
}

def first_hit_rank(hits: list[dict], expected: list[str]) -> int | None:
    """정답 파일이 처음 나온 순위(1부터). 파일 단위로 본다. 없으면 None."""
    for rank, hit in enumerate(hits, 1):
        if hit["path"] in expected:
            return rank
    return None


print(f"평가셋: {split} {len(questions)}문항, 판정: 상위 5개 안에 정답 파일이 있으면 맞음\n")
misses: dict[str, list[str]] = {}
for name, run in SETUPS.items():
    ranks = [first_hit_rank(run(q["question"]), q["expected_files"]) for q in questions]
    hit = sum(r is not None for r in ranks)
    mrr = sum(1 / r for r in ranks if r) / len(ranks)  # 정답이 위에 있을수록 1에 가깝다
    print(f"{name:18} recall@5 {hit}/{len(ranks)} ({hit / len(ranks):.0%})  MRR {mrr:.2f}")
    misses[name] = [q["id"] for q, r in zip(questions, ranks) if r is None]

print("\n놓친 질문:")
for name, ids in misses.items():
    print(f"  {name:18} {', '.join(ids) or '없음'}")