"""3.6 질문 10개로 ReAct와 계획-실행 비교 + 하루 처리 가능 문항 계산.
실행: uv run python scripts\\agent_eval.py react   (또는 plan)
결과는 evals/repo_pilot/reports/에 저장된다. 근거 타당성(O/X)은 저장된 답을 보고 직접 채운다."""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from agent_lab.agents.repo_pilot.agent import ask
from agent_lab.agents.repo_pilot.tools import RepoToolbox
from agent_lab.core.llm import LLMClient

EVALS = Path(__file__).resolve().parents[1] / "evals" / "repo_pilot"
CITE = re.compile(r"([\w./-]+\.(?:py|md)):(\d+)")  # 답 속의 '경로:줄'
# 하루 무료 한도 (1.4 표): Groq는 모델마다 따로 센다
DAILY = {"fast": (200_000, 1000), "smart": (200_000, 1000), "long": (None, 500)}  # (토큰, 요청)


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "react"
    model = sys.argv[2] if len(sys.argv) > 2 else "fast"
    lines = (EVALS / "dev_qa.jsonl").read_text(encoding="utf-8").splitlines()
    questions = [json.loads(line) for line in lines if line][:10]  # 개발용 앞 10개
    rows = []
    async with LLMClient() as client:
        toolbox = RepoToolbox("httpx")
        for q in questions:
            r = await ask(client, q["question"], toolbox, model=model, mode=mode)
            cited = sorted({m.group(1) for m in CITE.finditer(r["text"])})
            file_match = any(p in q["expected_files"] for p in cited)
            rows.append({
                "id": q["id"], "question": q["question"], "expected_files": q["expected_files"],
                "answer": r["text"], "cited": cited, "file_match": file_match,
                "grounded": None,  # ← 사람이 채운다: 인용한 줄이 주장을 실제로 뒷받침하면 true
                "steps": r["steps"], "calls": r["calls"], "tokens": r["tokens"], "stopped": r["stopped"], "model": r["model"],
            })
            print(f"{q['id']} {'O' if file_match else 'X'} 단계 {r['steps']} 호출 {r['calls']} {r['tokens']:>6}토큰 {r['stopped']:9} 인용 {', '.join(cited) or '없음'}")

    n = len(rows)
    tok = sum(r["tokens"] for r in rows) / n
    calls = sum(r["calls"] for r in rows) / n
    print(f"\n[{mode}/{model}] 파일 일치 {sum(r['file_match'] for r in rows)}/{n}, 평균 단계 {sum(r['steps'] for r in rows) / n:.1f}, "
          f"평균 호출 {calls:.1f}회, 평균 {tok:,.0f}토큰, max_steps 도달 {sum(r['stopped'] == 'max_steps' for r in rows)}건")
    tpd, rpd = DAILY.get(model, (None, None))
    by_tokens = f"{tpd / tok:.0f}" if tpd else "한도 없음"
    limits = [x for x in (tpd and tpd / tok, rpd and rpd / calls) if x]
    if limits:
        print(f"하루 처리 가능 문항(이 모델 하나로): 약 {min(limits):.0f}문항  (토큰 기준 {by_tokens}, 요청 기준 {rpd / calls:.0f})")

    out = EVALS / "reports" / f"agent_{mode}_{model}_{datetime.now():%Y%m%d_%H%M}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out.relative_to(EVALS.parents[1])}  ← grounded 칸을 직접 채운다")


asyncio.run(main())