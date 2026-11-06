"""3.2 두 청킹 방식 비교. 실행: uv run python scripts\\chunk_stats.py httpx"""

import sys
from collections import Counter

from agent_lab.agents.repo_pilot.chunking import chunk_file
from agent_lab.agents.repo_pilot.ingest import REPOS_DIR, collect

name = sys.argv[1] if len(sys.argv) > 1 else "httpx"
root = REPOS_DIR / name
records, _ = collect(root)

for strategy in ("A", "B"):
    chunks = [c for r in records for c in chunk_file(r, root, strategy)]
    lines = [c.end_line - c.start_line + 1 for c in chunks]
    chars = [len(c.text) for c in chunks]
    kinds = Counter(c.kind for c in chunks)
    print(
        f"방식 {strategy}: 청크 {len(chunks)}개, 평균 {sum(lines) / len(lines):.1f}줄 "
        f"/ {sum(chars) / len(chars):.0f}자, 가장 긴 청크 {max(chars)}자, 종류 {dict(kinds)}"
    )

# 방식 B가 실제로 어떻게 잘랐는지 한 파일만 보기
sample = next(r for r in records if r.path.endswith("_client.py"))
for c in chunk_file(sample, root, "B")[:8]:
    print(f"  {c.path}:{c.start_line}-{c.end_line}  [{c.kind}] {c.symbol}")