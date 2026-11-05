"""1.6 도구 인자를 Pydantic으로 검증하는 버전. 1.5의 tools.py를 이 내용으로 바꾼다."""

import ast
import json
import operator

from pydantic import BaseModel, Field, ValidationError

# ---------- 도구 함수 (1.5와 같음) ----------
WEATHER = {
    "seoul": {"temp_c": 21, "sky": "맑음"},
    "busan": {"temp_c": 24, "sky": "흐림"},
    "jeju": {"temp_c": 26, "sky": "비"},
}


def get_weather(city: str) -> dict:
    data = WEATHER.get(city.strip().lower())
    if data is None:
        return {"error": f"'{city}' 날씨 정보 없음. 가능한 도시: {', '.join(WEATHER)}"}
    return {"city": city, **data}


OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    raise ValueError("숫자와 + - * / 괄호만 쓸 수 있습니다")


def calculate(expression: str) -> dict:
    try:
        return {
            "expression": expression,
            "result": _eval(ast.parse(expression, mode="eval").body),
        }
    except ZeroDivisionError:
        return {"error": "0으로 나눌 수 없습니다"}
    except (ValueError, SyntaxError) as e:
        return {"error": str(e)}


# ---------- 1.6 새로 추가: 인자를 Pydantic 모델로 정의 ----------
class WeatherArgs(BaseModel):
    # Field의 description은 그대로 JSON Schema에 들어가 모델에게 보인다
    city: str = Field(min_length=2, max_length=30, description="영어 도시 이름. 예: Seoul")


class CalcArgs(BaseModel):
    expression: str = Field(
        min_length=1, max_length=100, description="사칙연산 수식. 예: 21 * 9 / 5 + 32"
    )


def tool_spec(name: str, description: str, args_model: type[BaseModel]) -> dict:
    """도구 설명을 만든다. parameters는 Pydantic 모델에서 자동으로 만든다 (손으로 두 번 안 씀)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": args_model.model_json_schema(),
        },
    }


TOOLS = [
    tool_spec(
        "get_weather",
        "도시의 현재 날씨(섭씨 기온, 하늘 상태)를 조회한다. 날씨를 물을 때만 쓴다.",
        WeatherArgs,
    ),
    tool_spec(
        "calculate",
        "사칙연산 수식을 계산한다. 숫자 계산이 필요하면 반드시 이 도구를 쓴다.",
        CalcArgs,
    ),
]

# 도구 이름 → (인자 모델, 실제 함수)
REGISTRY = {
    "get_weather": (WeatherArgs, get_weather),
    "calculate": (CalcArgs, calculate),
}


def summarize(e: ValidationError) -> str:
    """검증 오류를 '필드: 이유' 형태로 짧게 줄인다 (길면 컨텍스트 낭비)."""
    # e.errors()는 오류마다 loc(어느 필드)과 msg(무슨 규칙)를 준다
    return "; ".join(
        f"{'.'.join(map(str, err['loc'])) or '전체'}: {err['msg']}"
        for err in e.errors()
    )


def run_tool(name: str, arguments_json: str) -> tuple[str, bool]:
    """도구를 검증 후 실행한다. (모델에게 돌려줄 글, 인자 검증 통과 여부)를 돌려준다."""
    if name not in REGISTRY:
        return f"알 수 없는 도구: {name}. 쓸 수 있는 도구: {', '.join(REGISTRY)}", False
    args_model, func = REGISTRY[name]
    try:
        # 글자(JSON) → 검증된 객체. 형식이 틀리거나 규칙(min_length 등)을 어기면 ValidationError
        args = args_model.model_validate_json(arguments_json)
    except ValidationError as e:
        # 실패를 모델에게 돌려줘서 스스로 고치게 한다
        return f"인자 오류: {summarize(e)}. 인자를 고쳐서 다시 호출하라.", False
    result = func(**args.model_dump())  # 검증된 값만 함수에 넣는다
    return json.dumps(result, ensure_ascii=False), True