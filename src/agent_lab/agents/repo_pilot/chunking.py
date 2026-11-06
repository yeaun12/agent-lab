"""3.2 청킹: 파일을 검색 단위(청크)로 자른다. 방식 A = 고정 크기, 방식 B = 코드 구조(ast)."""

import ast
import hashlib
from pathlib import Path

from pydantic import BaseModel

from agent_lab.agents.repo_pilot.ingest import FileRecord

# 청크 하나의 상한. nomic-embed-text는 2048토큰이 넘으면 뒤를 말없이 잘라 버린다.
# 코드는 대략 3글자에 1토큰이라 4,000자 ≈ 1,300토큰 → 안전하게 2048 아래에 머문다.
MAX_LINES = 120
MAX_CHARS = 4000


class Chunk(BaseModel):
    id: str  # path와 start_line으로 만든 고정 ID. 다시 색인해도 같은 청크는 같은 ID
    path: str  # 저장소 기준 경로
    start_line: int  # 1부터 시작 (에디터에 보이는 줄 번호와 같게)
    end_line: int  # 이 줄까지 포함
    symbol: str  # 함수·클래스 이름(예: Client.send), 문서 제목, 또는 파일 이름
    kind: str  # function, class, module, doc, text
    text: str  # 임베딩할 글 = 위치 헤더 + 본문


def make_chunk(path: str, lines: list[str], start: int, end: int, symbol: str, kind: str) -> Chunk:
    """줄 범위(start~end, 1부터)로 청크를 만든다. 본문 앞에 위치 헤더를 붙인다."""
    body = "\n".join(lines[start - 1 : end])
    # 헤더: 임베딩에 '어느 파일의 무엇인지'를 함께 넣어 검색이 경로·이름에도 반응하게 한다
    header = f"# file: {path} / symbol: {symbol}\n"
    cid = hashlib.sha256(f"{path}:{start}".encode()).hexdigest()[:32]
    return Chunk(id=cid, path=path, start_line=start, end_line=end, symbol=symbol, kind=kind, text=header + body)


def split_long(path: str, lines: list[str], start: int, end: int, symbol: str, kind: str) -> list[Chunk]:
    """범위가 상한(MAX_LINES 줄, MAX_CHARS 글자)을 넘으면 여러 조각으로 나눈다."""
    out, s = [], start
    while s <= end:
        e, chars = s, 0
        # 줄을 하나씩 더하다가 상한에 닿으면 멈춘다 (최소 한 줄은 넣는다)
        while e <= end and e - s < MAX_LINES and (chars + len(lines[e - 1]) < MAX_CHARS or e == s):
            chars += len(lines[e - 1]) + 1
            e += 1
        part = symbol if (s == start and e > end) else f"{symbol} (part {len(out) + 1})"
        out.append(make_chunk(path, lines, s, e - 1, part, kind))
        s = e
    return out


# ---------- 방식 A: 고정 크기 ----------
def chunk_fixed(path: str, text: str, size: int = 60, overlap: int = 10) -> list[Chunk]:
    """size줄씩 자르고 overlap줄씩 겹친다. 겹치면 경계에 걸친 코드도 한쪽에는 온전히 들어간다."""
    lines = text.splitlines()
    kind = "doc" if path.endswith(".md") else "text"
    out = []
    for start in range(1, max(len(lines), 1) + 1, size - overlap):
        end = min(start + size - 1, len(lines))
        out.extend(split_long(path, lines, start, end, Path(path).name, kind))
        if end == len(lines):
            break
    return out


# ---------- 방식 B: 코드 구조 ----------
def node_start(node: ast.AST) -> int:
    """데코레이터(@...)가 있으면 그 줄부터 시작으로 본다."""
    decos = getattr(node, "decorator_list", [])
    return min([d.lineno for d in decos] + [node.lineno])


def chunk_python(path: str, text: str) -> list[Chunk]:
    """함수·클래스·메서드 경계로 자른다. 어디에도 속하지 않은 줄(임포트, 상수)은 module 청크로."""
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:  # 문법이 깨진 파일은 방식 A로 대신한다
        return chunk_fixed(path, text)
    out, covered = [], set()
    defs = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in tree.body:
        if isinstance(node, defs):
            s, e = node_start(node), node.end_lineno
            out += split_long(path, lines, s, e, node.name, "function")
            covered.update(range(s, e + 1))
        elif isinstance(node, ast.ClassDef):
            s, e = node_start(node), node.end_lineno
            methods = [n for n in node.body if isinstance(n, defs)]
            # 클래스 머리(선언, docstring, 클래스 변수) = 첫 메서드 전까지
            head_end = (node_start(methods[0]) - 1) if methods else e
            out += split_long(path, lines, s, head_end, node.name, "class")
            for m in methods:
                out += split_long(path, lines, node_start(m), m.end_lineno, f"{node.name}.{m.name}", "function")
            covered.update(range(s, e + 1))
    # 남은 줄을 이어지는 덩어리끼리 묶어 module 청크로 만든다
    run: list[int] = []
    for n in range(1, len(lines) + 2):
        if n <= len(lines) and n not in covered:
            run.append(n)
            continue
        # 덩어리 앞뒤의 빈 줄은 떼어 낸다 (줄 범위가 실제 내용과 맞게)
        while run and not lines[run[0] - 1].strip():
            run.pop(0)
        while run and not lines[run[-1] - 1].strip():
            run.pop()
        if run:
            out += split_long(path, lines, run[0], run[-1], Path(path).stem + " (module)", "module")
        run = []
    return sorted(out, key=lambda c: c.start_line)


def chunk_markdown(path: str, text: str) -> list[Chunk]:
    """# 제목 줄마다 자른다. ``` 코드 블록 안의 # 은 제목이 아니므로 건너뛴다."""
    lines = text.splitlines()
    starts, titles, in_code = [], [], False
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code and line.startswith("#"):
            starts.append(n)
            titles.append(line.lstrip("#").strip() or Path(path).name)
    if not starts or starts[0] != 1:  # 첫 제목 앞의 글도 한 청크로
        starts.insert(0, 1)
        titles.insert(0, Path(path).name)
    out = []
    for i, s in enumerate(starts):
        e = starts[i + 1] - 1 if i + 1 < len(starts) else len(lines)
        if any(line.strip() for line in lines[s - 1 : e]):
            out += split_long(path, lines, s, e, titles[i], "doc")
    return out


def chunk_file(record: FileRecord, root: Path, strategy: str) -> list[Chunk]:
    """strategy='A'면 고정 크기, 'B'면 파이썬은 ast·문서는 제목·나머지는 고정 크기."""
    text = (root / record.path).read_text(encoding="utf-8")
    if strategy == "A":
        return chunk_fixed(record.path, text)
    if record.lang == "python":
        return chunk_python(record.path, text)
    if record.lang == "markdown":
        return chunk_markdown(record.path, text)
    return chunk_fixed(record.path, text)