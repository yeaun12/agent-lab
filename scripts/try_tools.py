"""3.5 도구를 모델 없이 직접 불러 본다. 실행: uv run python scripts\try_tools.py"""

from agent_lab.agents.repo_pilot.tools import RepoToolbox

box = RepoToolbox("httpx")
CALLS = [
    ("read_file", '{"path": "httpx/_config.py", "start_line": 244, "end_line": 248}'),
    ("grep", '{"pattern": "DEFAULT_MAX_REDIRECTS", "path_glob": "httpx/*.py"}'),
    ("list_dir", '{"path": "httpx/_transports"}'),
    ("read_file", '{"path": "../../Windows/win.ini"}'),  # 경로 탈출 시도
    ("read_file", '{"path": "httpx/_config.py", "start_line": 0}'),  # 인자 규칙 위반
    ("search_code", '{"query": "default timeout config", "k": 2}'),
]
for name, args in CALLS:
    text, ok = box.run(name, args)  # 모델이 도구를 부를 때와 똑같은 호출
    print(f">>> {name} {args}\nok={ok}\n{text}\n")