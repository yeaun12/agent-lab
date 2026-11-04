"""앱 설정. .env 파일과 환경 변수에서 값을 읽어 온다."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_file=".env": 프로젝트 폴더의 .env를 읽는다 (uv run을 프로젝트 폴더에서 실행해야 찾는다)
    # extra="ignore": .env에 여기 없는 이름이 있어도 오류 없이 무시한다
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 앱 이름. .env에 APP_NAME=... 이 없으면 기본값을 쓴다
    app_name: str = "agent-lab"

    # API 키는 SecretStr로 받는다 → print나 로그에 찍혀도 '**********'로 가려진다
    # .env의 GROQ_API_KEY → groq_api_key 처럼 대소문자 구분 없이 이름이 연결된다
    groq_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")


@lru_cache  # 처음 한 번만 Settings()를 만들고, 다음부터는 만든 것을 그대로 돌려준다
def get_settings() -> Settings:
    return Settings()
