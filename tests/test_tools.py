"""1.6 도구 테스트. run_tool이 (결과 글, 검증 통과 여부)를 돌려주는 버전."""

import json

from agent_lab.core.tools import TOOLS, calculate, get_weather, run_tool


def test_calculate_basic():
    assert calculate("2 * (3 + 4)")["result"] == 14


def test_calculate_blocks_code():
    assert "error" in calculate("__import__('os').system('dir')")


def test_weather_unknown_city():
    assert "error" in get_weather("Atlantis")


def test_run_tool_ok():
    text, ok = run_tool("get_weather", '{"city": "Seoul"}')
    assert ok
    assert json.loads(text)["temp_c"] == 21


def test_run_tool_validation_error():
    # city가 1글자라 min_length=2 규칙에 걸려야 한다
    text, ok = run_tool("get_weather", '{"city": "S"}')
    assert not ok
    assert text.startswith("인자 오류: city")


def test_schema_comes_from_pydantic():
    params = TOOLS[0]["function"]["parameters"]
    assert params["properties"]["city"]["minLength"] == 2  # Field(min_length=2)가 스키마에 들어감