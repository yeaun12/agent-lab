"""3.1 수집 통계. 실행: uv run python scripts\\repo_stats.py httpx"""

import sys
from collections import Counter

from agent_lab.agents.repo_pilot.ingest import REPOS_DIR, collect

name = sys.argv[1] if len(sys.argv) > 1 else "httpx"
records, skipped = collect(REPOS_DIR / name)

print(f"모은 파일: {len(records)}개, 총 {sum(r.lines for r in records):,}줄")
by_lang = Counter()
for r in records:
    by_lang[r.lang] += r.lines
for lang, lines in by_lang.most_common():
    count = sum(1 for r in records if r.lang == lang)
    print(f"  {lang:9} {count:4}개 {lines:7,}줄")
print("뺀 파일:", dict(skipped))
biggest = max(records, key=lambda r: r.lines)
print(f"가장 긴 파일: {biggest.path} ({biggest.lines:,}줄)")