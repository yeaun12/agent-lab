"""3.5 코드베이스 도구 4개. 모델이 저장소를 '검색하고, 열어 보고, 둘러보고, 찾게' 한다.
1.6과 같은 방식: 인자는 Pydantic으로 검증하고, 결과와 실패는 모두 글로 돌려준다."""

import fnmatch
import re
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError

from agent_lab.agents.repo_pilot.ingest import REPOS_DIR, SKIP_DIRS, collect
from agent_lab.agents.repo_pilot.retrieval import hybrid_search
from agent_lab.core.tools import summarize, tool_spec

READ_MAX_LINES = 80  # Groq 무료 등급은 요청 하나가 8K 토큰을 넘으면 413 → 결과 하나를 작게
GREP_MAX = 30
LINE_MAX_CHARS = 120
LIST_MAX = 100


class ToolError(Exception):
    """모델에게 그대로 보여 줄 실패 (예외로 프로그램을 멈추지 않는다)."""


# ---------- 인자 모델: 이 모양이 그대로 모델에게 보이는 스키마가 된다 ----------
class SearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200, description="찾고 싶은 내용. 영어 코드 이름을 섞으면 더 잘 찾는다")
    k: int = Field(default=5, ge=1, le=8, description="돌려받을 결과 수")


class ReadArgs(BaseModel):
    path: str = Field(description="저장소 기준 파일 경로. 예: httpx/_client.py")
    start_line: int = Field(default=1, ge=1, description="읽기 시작할 줄 (1부터)")
    end_line: int | None = Field(default=None, ge=1, description="여기까지 읽는다. 비우면 최대 80줄")


class ListArgs(BaseModel):
    path: str = Field(default=".", description="저장소 기준 폴더 경로. 예: httpx/_transports")


class GrepArgs(BaseModel):
    pattern: str = Field(min_length=1, max_length=100, description="찾을 정규식. 예: def raise_for_status")
    path_glob: str = Field(default="**/*.py", description="찾을 파일 범위. 예: httpx/*.py")


class RepoToolbox:
    def __init__(self, repo: str = "httpx", root: Path | None = None, collection: str | None = None):
        self.repo = repo
        self.root = (root or REPOS_DIR / repo).resolve()
        self.collection = collection or f"{repo}_B_p"
        self.registry = {
            "search_code": (SearchArgs, self.search_code),
            "read_file": (ReadArgs, self.read_file),
            "list_dir": (ListArgs, self.list_dir),
            "grep": (GrepArgs, self.grep),
        }
        self.specs = [
            tool_spec("search_code", "저장소에서 질문과 관련된 코드·문서 조각을 찾는다. 어디서부터 볼지 모를 때 먼저 쓴다.", SearchArgs),
            tool_spec("read_file", "파일의 일부를 줄 번호와 함께 읽는다. 답의 근거(path:line)를 확인할 때 쓴다.", ReadArgs),
            tool_spec("list_dir", "폴더 안의 파일과 하위 폴더 목록을 본다. 실제 경로를 모를 때 쓴다.", ListArgs),
            tool_spec("grep", "정규식으로 정확한 이름(함수, 상수, 환경 변수)을 찾는다. 이름을 알 때 search_code보다 정확하다.", GrepArgs),
        ]

    # ---------- 경로 안전 ----------
    def safe_path(self, rel: str) -> Path:
        """저장소 루트 밖으로 나가는 경로를 막는다. '../../', 절대 경로, 다른 드라이브 모두."""
        target = (self.root / rel).resolve()  # resolve: ..을 풀고 실제 위치로 바꾼다
        if not target.is_relative_to(self.root):
            raise ToolError(f"'{rel}'은(는) 저장소 밖 경로라 열 수 없다. 저장소 기준 경로를 쓴다(예: httpx/_client.py).")
        if any(part in SKIP_DIRS for part in target.relative_to(self.root).parts):
            raise ToolError(f"'{rel}'은(는) 제외 폴더(.git 등) 안이라 열 수 없다.")
        return target

    # ---------- 도구 4개 ----------
    def search_code(self, query: str, k: int = 5) -> str:
        try:
            hits = hybrid_search(query, self.repo, "B", self.collection, k=k)
        except (RuntimeError, ValueError, httpx.HTTPError) as e:
            # 색인 폴더를 다른 프로그램이 쓰는 중(RuntimeError), 컬렉션 없음(ValueError), Ollama 꺼짐(HTTPError)
            raise ToolError(f"검색 색인을 쓸 수 없다({type(e).__name__}). grep과 read_file로 찾는다.") from e
        out = []
        for h in hits:
            body = h["text"].split("\n")[1:7]  # 헤더 줄을 빼고 앞 6줄만 미리 보기
            preview = "\n".join("    " + line[:LINE_MAX_CHARS] for line in body)
            out.append(f"{h['path']}:{h['start_line']}-{h['end_line']} [{h['kind']}] {h['symbol']}\n{preview}")
        return "\n".join(out) or "결과 없음. 다른 단어나 grep을 써 본다."

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> str:
        target = self.safe_path(path)
        if not target.is_file():
            raise ToolError(f"'{path}' 파일이 없다. list_dir로 실제 경로를 먼저 확인한다.")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if start_line > len(lines):
            raise ToolError(f"'{path}'은(는) {len(lines)}줄이다. start_line을 그보다 작게 준다.")
        last = min(end_line or len(lines), len(lines), start_line + READ_MAX_LINES - 1)
        body = "\n".join(f"{n}: {lines[n - 1][:200]}" for n in range(start_line, last + 1))
        note = ""
        if last < (end_line or len(lines)):
            note = f"\n(잘림: 최대 {READ_MAX_LINES}줄. 이어서 보려면 start_line={last + 1})"
        return f"{path}:{start_line}-{last}\n{body}{note}"

    def list_dir(self, path: str = ".") -> str:
        target = self.safe_path(path)
        if not target.is_dir():
            raise ToolError(f"'{path}' 폴더가 없다.")
        entries = sorted(
            (p.name + "/" if p.is_dir() else p.name) for p in target.iterdir() if p.name not in SKIP_DIRS
        )
        more = f"\n(그 밖에 {len(entries) - LIST_MAX}개)" if len(entries) > LIST_MAX else ""
        return "\n".join(entries[:LIST_MAX]) + more

    def grep(self, pattern: str, path_glob: str = "**/*.py") -> str:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"정규식 오류: {e}. 특수문자는 \\로 이스케이프한다.") from e
        records, _ = collect(self.root)  # 3.1 규칙 그대로: 텍스트 파일만, 제외 폴더 빼고
        out = []
        for r in records:
            # '**/*.py'는 최상위 파일도 포함하도록 '*.py'로도 맞춰 본다
            if not (fnmatch.fnmatch(r.path, path_glob) or fnmatch.fnmatch(r.path, path_glob.removeprefix("**/"))):
                continue
            for n, line in enumerate((self.root / r.path).read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(line):
                    out.append(f"{r.path}:{n}: {line.strip()[:LINE_MAX_CHARS]}")
                    if len(out) >= GREP_MAX:
                        return "\n".join(out) + f"\n(최대 {GREP_MAX}개에서 멈춤. pattern이나 path_glob을 좁힌다)"
        return "\n".join(out) or "일치 없음."

    # ---------- 실행 (2.6 run_tool과 같은 모양) ----------
    def run(self, name: str, arguments_json: str) -> tuple[str, bool]:
        """(모델에게 돌려줄 글, 성공 여부). 어떤 실패도 예외로 새지 않게 글로 바꾼다."""
        if name not in self.registry:
            return f"없는 도구: {name}. 쓸 수 있는 도구: {', '.join(self.registry)}", False
        args_model, func = self.registry[name]
        try:
            args = args_model.model_validate_json(arguments_json or "{}")
        except ValidationError as e:
            return f"인자 오류: {summarize(e)}", False
        try:
            return func(**args.model_dump()), True
        except ToolError as e:
            return f"오류: {e}", False