"""3.3 의미 검색 해 보기. 실행: uv run python scripts\\search.py "재시도는 어디서 하나" httpx_B_p"""

import sys

from agent_lab.agents.repo_pilot.index import search

query = sys.argv[1]
collection = sys.argv[2] if len(sys.argv) > 2 else "httpx_B_p"
folder = sys.argv[3] if len(sys.argv) > 3 else None  # 예: httpx/_transports

for hit in search(query, collection, k=5, folder=folder):
    print(f"{hit['score']:.3f}  {hit['path']}:{hit['start_line']}-{hit['end_line']}  [{hit['kind']}] {hit['symbol']}")