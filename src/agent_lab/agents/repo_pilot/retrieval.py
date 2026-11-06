"""3.4 키워드 검색(BM25)과 하이브리드 검색(RRF)."""

import re
from functools import lru_cache

from rank_bm25 import BM25Okapi

from agent_lab.agents.repo_pilot.chunking import Chunk, chunk_file
from agent_lab.agents.repo_pilot.index import search
from agent_lab.agents.repo_pilot.ingest import REPOS_DIR, collect


def tokenize(text: str) -> list[str]:
    """글을 검색용 단어로 나눈다. 코드 이름은 쪼개서도 넣는다.
    'raise_for_status' → raise_for_status, raise, for, status / 'AsyncClient' → asyncclient, async, client"""
    tokens = []
    for word in re.findall(r"\w+", text):  # \w는 한글도 포함한다
        tokens.append(word.lower())
        parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", word)  # 밑줄과 대소문자 경계로 쪼개기
        if len(parts) > 1:
            tokens += [p.lower() for p in parts]
    return tokens


@lru_cache  # 같은 저장소·방식이면 한 번만 만든다
def bm25_index(repo: str, strategy: str) -> tuple[BM25Okapi, list[Chunk]]:
    root = REPOS_DIR / repo
    records, _ = collect(root)
    chunks = [c for r in records for c in chunk_file(r, root, strategy)]
    return BM25Okapi([tokenize(c.text) for c in chunks]), chunks


def bm25_search(query: str, repo: str, strategy: str, k: int = 5) -> list[dict]:
    bm25, chunks = bm25_index(repo, strategy)
    scores = bm25.get_scores(tokenize(query))
    top = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:k]
    return [{"score": round(float(scores[i]), 3), **chunks[i].model_dump()} for i in top]


def rrf(result_lists: list[list[dict]], k: int = 5, c: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion: 각 목록에서의 순위만 보고 점수를 합친다. 점수 1/(c + 순위).
    벡터 점수(0~1)와 BM25 점수(0~수십)는 단위가 달라 직접 더할 수 없어서 순위를 쓴다."""
    fused: dict[str, float] = {}
    items: dict[str, dict] = {}
    for results in result_lists:
        for rank, hit in enumerate(results, 1):
            fused[hit["id"]] = fused.get(hit["id"], 0) + 1 / (c + rank)
            items[hit["id"]] = hit
    best = sorted(fused, key=fused.get, reverse=True)[:k]
    return [{**items[i], "score": round(fused[i], 4)} for i in best]


def hybrid_search(query: str, repo: str, strategy: str, collection: str, k: int = 5, drop_tests: bool = False) -> list[dict]:
    """벡터 상위 20개와 BM25 상위 20개를 RRF로 합쳐 k개. drop_tests=True면 tests/ 결과를 빼고 합친다."""
    pool = 30 if drop_tests else 20  # 빼고 나면 줄어드니 처음에 더 많이 가져온다
    vec = search(query, collection, k=pool)
    kw = bm25_search(query, repo, strategy, k=pool)
    if drop_tests:  # 테스트는 '어떻게 쓰나'의 예시라 '어디에 구현됐나' 질문에서는 정답을 밀어낸다
        vec = [h for h in vec if not h["path"].startswith("tests/")]
        kw = [h for h in kw if not h["path"].startswith("tests/")]
    return rrf([vec, kw], k=k)