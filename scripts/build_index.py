"""3.3 색인 만들기. 실행: uv run python scripts\\build_index.py httpx B
접두어 없이 만들려면 끝에 --no-prefix (3.4 비교용)."""

import sys

from agent_lab.agents.repo_pilot.index import build_index

repo = sys.argv[1] if len(sys.argv) > 1 else "httpx"
strategy = sys.argv[2] if len(sys.argv) > 2 else "B"
prefix = "--no-prefix" not in sys.argv

result = build_index(repo, strategy, prefix)
for key, value in result.items():
    print(f"{key:16} {value}")