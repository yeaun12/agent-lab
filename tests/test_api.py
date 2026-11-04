"""1.2 API 테스트. 서버를 켜지 않고 앱을 직접 불러서 확인한다."""

from httpx import ASGITransport, AsyncClient

from agent_lab.api import app


def make_client():
    # ASGITransport: 네트워크 대신 app을 직접 호출하는 통로. base_url은 아무 주소나 써도 된다
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health():
    async with make_client() as client:
        r = await client.get("/health")
    assert r.status_code == 200  # 정상 응답
    assert r.json()["status"] == "ok"  # 본문 확인


async def test_echo_ok():
    async with make_client() as client:
        r = await client.post("/echo", json={"text": "hi", "repeat": 3})
    assert r.status_code == 200
    assert r.json() == {"result": "hi hi hi"}


async def test_echo_invalid():
    async with make_client() as client:
        r = await client.post("/echo", json={"text": "hi", "repeat": 10})
    assert r.status_code == 422  # repeat은 5까지라 검증 오류가 나야 맞다


async def test_echo_upper():
    async with make_client() as client:
        r = await client.post("/echo", json={"text": "hi", "repeat": 2, "upper": True})
    assert r.json() == {"result": "HI HI"}
