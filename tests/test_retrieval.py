"""3.3·3.4 계산 부분 테스트 (Ollama·색인 없이 도는 것만)."""

from agent_lab.agents.repo_pilot.index import collection_name, dirs_of
from agent_lab.agents.repo_pilot.retrieval import rrf, tokenize


def test_tokenize_splits_code_names():
    assert tokenize("raise_for_status") == ["raise_for_status", "raise", "for", "status"]
    assert tokenize("AsyncClient 요청") == ["asyncclient", "async", "client", "요청"]


def test_rrf_prefers_items_high_in_both():
    vec = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    kw = [{"id": "b"}, {"id": "d"}, {"id": "a"}]
    assert [h["id"] for h in rrf([vec, kw], k=3)] == ["b", "a", "d"]


def test_dirs_and_names():
    assert dirs_of("httpx/_transports/default.py") == ["httpx", "httpx/_transports"]
    assert dirs_of("README.md") == []
    assert collection_name("httpx", "B", True) == "httpx_B_p"