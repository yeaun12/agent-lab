"""3.1 제외 규칙 테스트. tmp_path: pytest가 테스트마다 만들어 주는 빈 임시 폴더."""

from agent_lab.agents.repo_pilot.ingest import collect


def make(root, rel, content: bytes | str = "x = 1\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode("utf-8")
    path.write_bytes(content)


def test_collects_only_text_files(tmp_path):
    make(tmp_path, "pkg/a.py")
    make(tmp_path, "README.md", "# 제목\n")
    make(tmp_path, "logo.png", b"\x89PNG\x00\x00")  # 확장자로 빠짐
    records, skipped = collect(tmp_path)
    assert [r.path for r in records] == ["README.md", "pkg/a.py"]
    assert skipped["확장자"] == 1


def test_skips_git_and_build_dirs(tmp_path):
    make(tmp_path, ".git/config.py")
    make(tmp_path, "build/lib/x.py")
    make(tmp_path, "node_modules/m/index.md")
    make(tmp_path, "src/ok.py")
    records, skipped = collect(tmp_path)
    assert [r.path for r in records] == ["src/ok.py"]
    assert skipped["제외 폴더"] == 3


def test_skips_big_and_binary(tmp_path):
    make(tmp_path, "big.py", "a" * 1_000_001)  # 1MB 초과
    make(tmp_path, "bin.py", b"\x00\x01\x02")  # 확장자는 .py지만 바이너리
    records, skipped = collect(tmp_path)
    assert records == []
    assert skipped["1MB 초과"] == 1 and skipped["바이너리"] == 1


def test_record_fields(tmp_path):
    make(tmp_path, "m.py", "a = 1\nb = 2\n")
    (r,), _ = collect(tmp_path)
    assert r.lang == "python" and r.lines == 2 and len(r.sha256) == 64