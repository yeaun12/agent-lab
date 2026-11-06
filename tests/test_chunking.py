"""3.2 청킹 테스트. 줄 번호가 정확해야 나중에 'path:line' 인용이 맞는다."""

from agent_lab.agents.repo_pilot.chunking import (
    MAX_LINES,
    chunk_fixed,
    chunk_markdown,
    chunk_python,
)

CODE = '''import os

LIMIT = 3


@cache
def load(path):
    return open(path).read()


class Client:
    """도움말"""

    timeout = 5

    def send(self, req):
        return req

    async def close(self):
        pass
'''


def test_fixed_overlap():
    text = "\n".join(f"line {i}" for i in range(1, 121))  # 120줄
    chunks = chunk_fixed("a.py", text, size=60, overlap=10)
    assert [(c.start_line, c.end_line) for c in chunks] == [(1, 60), (51, 110), (101, 120)]


def test_python_boundaries():
    got = [(c.symbol, c.kind, c.start_line, c.end_line) for c in chunk_python("m.py", CODE)]
    assert got == [
        ("m (module)", "module", 1, 3),  # 임포트와 상수
        ("load", "function", 6, 8),  # 데코레이터 @cache 줄(6)부터 시작
        ("Client", "class", 11, 15),  # 클래스 머리: 선언, docstring, 클래스 변수
        ("Client.send", "function", 16, 17),
        ("Client.close", "function", 19, 20),  # async 메서드도 잡는다
    ]


def test_header_and_line_text():
    c = chunk_python("m.py", CODE)[1]
    assert c.text.startswith("# file: m.py / symbol: load\n@cache")


def test_long_function_is_split():
    body = "\n".join(f"    x{i} = {i}" for i in range(300))
    chunks = chunk_python("big.py", f"def huge():\n{body}\n")
    assert len(chunks) == 3  # 301줄 → 120 + 120 + 61
    assert chunks[0].symbol == "huge (part 1)"
    assert all(c.end_line - c.start_line + 1 <= MAX_LINES for c in chunks)


def test_syntax_error_falls_back_to_fixed():
    chunks = chunk_python("bad.py", "def broken(:\n    pass\n")
    assert chunks[0].kind == "text"


def test_markdown_ignores_hash_in_code_block():
    md = "# 시작\n글\n```bash\n# 이건 주석\n```\n## 설치\npip install httpx\n"
    got = [(c.symbol, c.start_line, c.end_line) for c in chunk_markdown("README.md", md)]
    assert got == [("시작", 1, 5), ("설치", 6, 7)]