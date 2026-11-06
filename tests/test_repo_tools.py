"""3.5 도구 테스트: 정상, 경계, 악의적 입력. 가짜 저장소(tmp_path)로 돌아서 색인이 필요 없다."""

import json

import pytest

from agent_lab.agents.repo_pilot.tools import READ_MAX_LINES, RepoToolbox


@pytest.fixture
def box(tmp_path):
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "a.py").write_text("\n".join(f"x{i} = {i}" for i in range(1, 201)), encoding="utf-8")
    (repo / "pkg" / "b.py").write_text("def retry():\n    pass\n", encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("secret", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("밖의 파일", encoding="utf-8")
    return RepoToolbox(repo="test", root=repo)


def call(box, name, **args):
    return box.run(name, json.dumps(args))


def test_read_file_ok(box):
    text, ok = call(box, "read_file", path="pkg/b.py")
    assert ok and text.startswith("pkg/b.py:1-2\n1: def retry():")


def test_read_file_is_capped(box):
    text, ok = call(box, "read_file", path="pkg/a.py")
    assert ok
    assert f"1-{READ_MAX_LINES}" in text.splitlines()[0]
    assert f"start_line={READ_MAX_LINES + 1}" in text  # 이어 읽는 방법을 알려 준다


@pytest.mark.parametrize("bad", ["../outside.txt", "../../outside.txt", "pkg/../../outside.txt", "C:/Windows/win.ini", "pkg\\..\\..\\outside.txt"])
def test_path_traversal_blocked(box, bad):
    text, ok = call(box, "read_file", path=bad)
    assert not ok and "저장소 밖" in text


def test_git_folder_blocked(box):
    text, ok = call(box, "read_file", path=".git/config")
    assert not ok and "제외 폴더" in text


def test_missing_file_has_hint(box):
    text, ok = call(box, "read_file", path="pkg/none.py")
    assert not ok and "list_dir" in text


def test_list_dir_hides_git(box):
    text, ok = call(box, "list_dir", path=".")
    assert ok and text == "pkg/"


def test_grep_finds_and_caps(box):
    text, ok = call(box, "grep", pattern=r"def retry")
    assert ok and text == "pkg/b.py:1: def retry():"
    text, ok = call(box, "grep", pattern=r"x\d+ =")
    assert "최대 30개에서 멈춤" in text


def test_grep_bad_regex(box):
    text, ok = call(box, "grep", pattern="(")
    assert not ok and "정규식 오류" in text


def test_validation_error(box):
    text, ok = call(box, "read_file", path="pkg/a.py", start_line=0)
    assert not ok and text.startswith("인자 오류: start_line")


def test_unknown_tool(box):
    text, ok = box.run("delete_repo", "{}")
    assert not ok and "search_code" in text