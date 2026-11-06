"""3.1 저장소 수집: 분석할 텍스트 파일만 골라 FileRecord 목록으로 만든다."""

import hashlib
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

# 이 파일(src/agent_lab/agents/repo_pilot/ingest.py)에서 네 단계 위 = 프로젝트 폴더
PROJECT = Path(__file__).resolve().parents[4]
REPOS_DIR = PROJECT / "data" / "repos"  # clone한 저장소를 두는 곳 (.gitignore에 넣는다)

# 모을 확장자 → 언어 이름
LANG = {".py": "python", ".md": "markdown", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml"}
# 폴더 이름이 이 중 하나면 그 아래는 통째로 건너뛴다
SKIP_DIRS = {".git", "node_modules", "build", "dist", "__pycache__", ".venv", "venv", ".mypy_cache"}
MAX_BYTES = 1_000_000  # 1MB가 넘는 파일은 사람이 쓴 코드가 아닐 가능성이 크다 (생성된 파일 등)


class FileRecord(BaseModel):
    path: str  # 저장소 폴더 기준 상대 경로, 항상 / 로 (Windows의 \ 를 바꿔 둔다)
    lang: str  # python, markdown, ...
    lines: int  # 줄 수
    size: int  # 바이트 수
    sha256: str  # 내용 해시. 3.3 증분 색인에서 '바뀐 파일만 다시' 판단에 쓴다


def skip_reason(path: Path, root: Path) -> str | None:
    """이 파일을 빼야 하면 이유를, 모아야 하면 None을 돌려준다 (테스트하기 쉽게 따로 뺐다)."""
    rel = path.relative_to(root)
    if any(part in SKIP_DIRS for part in rel.parts[:-1]):
        return "제외 폴더"
    if path.suffix.lower() not in LANG:
        return "확장자"
    if path.stat().st_size > MAX_BYTES:
        return "1MB 초과"
    return None


def read_text(path: Path) -> str | None:
    """UTF-8로 읽는다. 바이너리라 못 읽으면 None."""
    data = path.read_bytes()
    if b"\x00" in data[:1024]:  # 앞부분에 NUL 바이트가 있으면 바이너리로 본다
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def collect(root: Path) -> tuple[list[FileRecord], Counter]:
    """root 아래 파일을 돌며 (모은 파일 목록, 뺀 이유별 개수)를 돌려준다."""
    records, skipped = [], Counter()
    for path in root.rglob("*"):  # root 아래 모든 파일과 폴더
        if not path.is_file():
            continue
        reason = skip_reason(path, root)
        if reason is None:
            text = read_text(path)
            if text is None:
                reason = "바이너리"
        if reason:
            skipped[reason] += 1
            continue
        records.append(
            FileRecord(
                path=path.relative_to(root).as_posix(),
                lang=LANG[path.suffix.lower()],
                lines=len(text.splitlines()),  # 마지막 줄바꿈 뒤의 빈 줄은 세지 않는다
                size=path.stat().st_size,
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    # 경로 글자 순으로 정렬해 돌려준다 (Windows는 대소문자를 무시하고 정렬해서 OS마다 순서가 달라진다)
    return sorted(records, key=lambda r: r.path), skipped